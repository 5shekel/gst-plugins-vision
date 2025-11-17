/* GStreamer
 * Copyright (C) 2024 FIXME <fixme@example.com>
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Library General Public
 * License as published by the Free Software Foundation; either
 * version 2 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Library General Public License for more details.
 *
 * You should have received a copy of the GNU Library General Public
 * License along with this library; if not, write to the
 * Free Software Foundation, Inc., 59 Temple Place - Suite 330,
 * Boston, MA 02111-1307, USA.
 */

/**
 * SECTION:element-intervalometer
 *
 * Automatic exposure control for IDS uEye cameras.
 * Inspired by YASS (Yet Another Sunset Script) for CHDK cameras.
 * 
 * Analyzes video brightness and automatically adjusts camera exposure
 * and gain settings to maintain optimal exposure during changing light
 * conditions (e.g., sunset/sunrise time-lapse).
 *
 * <refsect2>
 * <title>Example launch line</title>
 * |[
 * gst-launch-1.0 idsueyesrc name=cam ! intervalometer enabled=true camera-element=cam ! videoconvert ! autovideosink
 * ]|
 * Automatically adjusts exposure and gain on the IDS uEye camera
 * </refsect2>
 */

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include "gstintervalometer.h"
#include <math.h>
#include <string.h>

GST_DEBUG_CATEGORY_STATIC (gst_intervalometer_debug);
#define GST_CAT_DEFAULT gst_intervalometer_debug

/* Properties */
enum
{
  PROP_0,
  PROP_ENABLED,
  PROP_TARGET_BRIGHTNESS,
  PROP_COMPENSATION,
  PROP_EXPOSURE_MIN,
  PROP_EXPOSURE_MAX,
  PROP_GAIN_MIN,
  PROP_GAIN_MAX,
  PROP_RAMP_RATE,
  PROP_LOG_FILE,
  PROP_CAMERA_ELEMENT,
  PROP_UPDATE_INTERVAL,
  PROP_BRIGHTNESS_SMOOTHING
};

#define DEFAULT_PROP_ENABLED TRUE
#define DEFAULT_PROP_TARGET_BRIGHTNESS 128.0
#define DEFAULT_PROP_COMPENSATION 0.0
#define DEFAULT_PROP_EXPOSURE_MIN 0.0  /* Will be queried from camera */
#define DEFAULT_PROP_EXPOSURE_MAX 0.0  /* Will be queried from camera */
#define DEFAULT_PROP_GAIN_MIN 0        /* Will be queried from camera */
#define DEFAULT_PROP_GAIN_MAX 0        /* Will be queried from camera */
#define DEFAULT_PROP_RAMP_RATE RAMP_RATE_MEDIUM
#define DEFAULT_PROP_LOG_FILE ""
#define DEFAULT_PROP_CAMERA_ELEMENT ""
#define DEFAULT_PROP_UPDATE_INTERVAL 100  /* Update every 100ms (10 Hz) */
#define DEFAULT_PROP_BRIGHTNESS_SMOOTHING 0.1  /* 10% new, 90% history - heavy smoothing for time-lapse */

/* GStreamer boilerplate */
#define gst_intervalometer_parent_class parent_class
G_DEFINE_TYPE (GstIntervalometer, gst_intervalometer, GST_TYPE_BASE_TRANSFORM);

/* Define the enum type for ramp rate */
#define GST_TYPE_INTERVALOMETER_RAMP_RATE (gst_intervalometer_ramp_rate_get_type ())
static GType
gst_intervalometer_ramp_rate_get_type (void)
{
  static GType ramp_rate_type = 0;
  static const GEnumValue ramp_rate_values[] = {
    {RAMP_RATE_VSLOW, "Very Slow", "vslow"},
    {RAMP_RATE_SLOW, "Slow", "slow"},
    {RAMP_RATE_MEDIUM, "Medium", "medium"},
    {RAMP_RATE_FAST, "Fast", "fast"},
    {RAMP_RATE_VFAST, "Very Fast", "vfast"},
    {0, NULL, NULL}
  };

  if (!ramp_rate_type) {
    ramp_rate_type = g_enum_register_static ("GstIntervalometerRampRate", ramp_rate_values);
  }
  return ramp_rate_type;
}

static GstStaticPadTemplate gst_intervalometer_sink_template =
GST_STATIC_PAD_TEMPLATE ("sink",
    GST_PAD_SINK,
    GST_PAD_ALWAYS,
    GST_STATIC_CAPS (GST_VIDEO_CAPS_MAKE ("{ GRAY8, GRAY16_LE, GRAY16_BE, BGRA, RGB, BGR }"))
    );

static GstStaticPadTemplate gst_intervalometer_src_template =
GST_STATIC_PAD_TEMPLATE ("src",
    GST_PAD_SRC,
    GST_PAD_ALWAYS,
    GST_STATIC_CAPS (GST_VIDEO_CAPS_MAKE ("{ GRAY8, GRAY16_LE, GRAY16_BE, BGRA, RGB, BGR }"))
    );

/* GObject vmethod declarations */
static void gst_intervalometer_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec);
static void gst_intervalometer_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec);
static void gst_intervalometer_dispose (GObject * object);
static void gst_intervalometer_finalize (GObject * object);

/* GstBaseTransform vmethod declarations */
static gboolean gst_intervalometer_start (GstBaseTransform * trans);
static gboolean gst_intervalometer_stop (GstBaseTransform * trans);
static gboolean gst_intervalometer_set_caps (GstBaseTransform * trans,
    GstCaps * incaps, GstCaps * outcaps);
static GstFlowReturn gst_intervalometer_transform_ip (GstBaseTransform * trans,
    GstBuffer * buf);

/* Helper functions */
static void gst_intervalometer_reset (GstIntervalometer * filter);
static gdouble gst_intervalometer_calculate_brightness (GstIntervalometer * filter,
    GstBuffer * buf);
static void gst_intervalometer_update_camera_settings (GstIntervalometer * filter,
    gdouble brightness);
static void gst_intervalometer_write_log (GstIntervalometer * filter,
    gdouble brightness);
static GstElement * gst_intervalometer_find_camera_element (GstIntervalometer * filter);
static gboolean gst_intervalometer_query_camera_capabilities (GstIntervalometer * filter);

/* Ramp rate multipliers (based on YASS algorithm) */
static const gdouble ramp_rate_multipliers[] = {
  0.5,  /* VSLOW */
  1.0,  /* SLOW */
  2.0,  /* MEDIUM */
  4.0,  /* FAST */
  8.0   /* VFAST */
};

static void
gst_intervalometer_class_init (GstIntervalometerClass * klass)
{
  GObjectClass *gobject_class = G_OBJECT_CLASS (klass);
  GstElementClass *gstelement_class = GST_ELEMENT_CLASS (klass);
  GstBaseTransformClass *gstbasetransform_class =
      GST_BASE_TRANSFORM_CLASS (klass);

  GST_DEBUG_CATEGORY_INIT (gst_intervalometer_debug, "intervalometer", 0,
      "Automatic Exposure Controller");

  /* Register GObject vmethods */
  gobject_class->set_property = gst_intervalometer_set_property;
  gobject_class->get_property = gst_intervalometer_get_property;
  gobject_class->dispose = gst_intervalometer_dispose;
  gobject_class->finalize = gst_intervalometer_finalize;

  /* Install GObject properties */
  g_object_class_install_property (gobject_class, PROP_ENABLED,
      g_param_spec_boolean ("enabled", "Enabled",
          "Enable automatic exposure control", DEFAULT_PROP_ENABLED,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_TARGET_BRIGHTNESS,
      g_param_spec_double ("target-brightness", "Target Brightness",
          "Target average brightness (0-255)", 0.0, 255.0,
          DEFAULT_PROP_TARGET_BRIGHTNESS,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_COMPENSATION,
      g_param_spec_double ("compensation", "Exposure Compensation",
          "Exposure compensation in stops", -4.0, 4.0,
          DEFAULT_PROP_COMPENSATION,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_EXPOSURE_MIN,
      g_param_spec_double ("exposure-min", "Minimum Exposure",
          "Minimum exposure time in milliseconds (0=query from camera)", 0.0, 10000.0,
          DEFAULT_PROP_EXPOSURE_MIN,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_EXPOSURE_MAX,
      g_param_spec_double ("exposure-max", "Maximum Exposure",
          "Maximum exposure time in milliseconds (0=query from camera)", 0.0, 10000.0,
          DEFAULT_PROP_EXPOSURE_MAX,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_GAIN_MIN,
      g_param_spec_int ("gain-min", "Minimum Gain",
          "Minimum gain value (0=query from camera)", 0, 1000, DEFAULT_PROP_GAIN_MIN,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_GAIN_MAX,
      g_param_spec_int ("gain-max", "Maximum Gain",
          "Maximum gain value (0=query from camera)", 0, 1000, DEFAULT_PROP_GAIN_MAX,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_RAMP_RATE,
      g_param_spec_enum ("ramp-rate", "Ramp Rate",
          "Speed of exposure/gain ramping", GST_TYPE_INTERVALOMETER_RAMP_RATE,
          DEFAULT_PROP_RAMP_RATE,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_LOG_FILE,
      g_param_spec_string ("log-file", "Log File",
          "Path to CSV log file (empty to disable logging)",
          DEFAULT_PROP_LOG_FILE,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_CAMERA_ELEMENT,
      g_param_spec_string ("camera-element", "Camera Element Name",
          "Name of the upstream camera element to control",
          DEFAULT_PROP_CAMERA_ELEMENT,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_UPDATE_INTERVAL,
      g_param_spec_uint ("update-interval", "Update Interval",
          "Interval between algorithm updates in milliseconds (0=every frame)",
          0, 10000, DEFAULT_PROP_UPDATE_INTERVAL,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_BRIGHTNESS_SMOOTHING,
      g_param_spec_double ("brightness-smoothing", "Brightness Smoothing",
          "Exponential smoothing factor for brightness (0=no smoothing, 1=no history). "
          "Lower values (0.05-0.2) filter out transient objects like people/cars. "
          "Recommended: 0.1 for dawn/dusk time-lapse",
          0.0, 1.0, DEFAULT_PROP_BRIGHTNESS_SMOOTHING,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  /* Set element metadata */
  gst_element_class_add_pad_template (gstelement_class,
      gst_static_pad_template_get (&gst_intervalometer_sink_template));
  gst_element_class_add_pad_template (gstelement_class,
      gst_static_pad_template_get (&gst_intervalometer_src_template));

  gst_element_class_set_static_metadata (gstelement_class,
      "Intervalometer Auto-Exposure", "Filter/Effect/Video",
      "Automatic exposure control for IDS uEye cameras (inspired by YASS)",
      "FIXME <fixme@example.com>");

  /* Register GstBaseTransform vmethods */
  gstbasetransform_class->start = GST_DEBUG_FUNCPTR (gst_intervalometer_start);
  gstbasetransform_class->stop = GST_DEBUG_FUNCPTR (gst_intervalometer_stop);
  gstbasetransform_class->set_caps =
      GST_DEBUG_FUNCPTR (gst_intervalometer_set_caps);
  gstbasetransform_class->transform_ip =
      GST_DEBUG_FUNCPTR (gst_intervalometer_transform_ip);
}

static void
gst_intervalometer_init (GstIntervalometer * filter)
{
  /* Initialize properties */
  filter->enabled = DEFAULT_PROP_ENABLED;
  filter->target_brightness = DEFAULT_PROP_TARGET_BRIGHTNESS;
  filter->compensation = DEFAULT_PROP_COMPENSATION;
  filter->exposure_min = DEFAULT_PROP_EXPOSURE_MIN;
  filter->exposure_max = DEFAULT_PROP_EXPOSURE_MAX;
  filter->gain_min = DEFAULT_PROP_GAIN_MIN;
  filter->gain_max = DEFAULT_PROP_GAIN_MAX;
  filter->ramp_rate = DEFAULT_PROP_RAMP_RATE;
  filter->log_file = g_strdup (DEFAULT_PROP_LOG_FILE);
  filter->camera_element_name = g_strdup (DEFAULT_PROP_CAMERA_ELEMENT);
  filter->update_interval = DEFAULT_PROP_UPDATE_INTERVAL;
  filter->brightness_smoothing = DEFAULT_PROP_BRIGHTNESS_SMOOTHING;

  /* Initialize internal state */
  filter->camera_src = NULL;
  filter->hCam = 0;
  filter->current_exposure = DEFAULT_PROP_EXPOSURE_MIN;
  filter->current_gain = DEFAULT_PROP_GAIN_MIN;
  filter->target_exposure = DEFAULT_PROP_EXPOSURE_MIN;
  filter->target_gain = DEFAULT_PROP_GAIN_MIN;
  filter->frame_count = 0;
  filter->start_time = GST_CLOCK_TIME_NONE;
  filter->last_update_time = GST_CLOCK_TIME_NONE;
  filter->log_fp = NULL;
  filter->log_header_written = FALSE;
  filter->video_info_valid = FALSE;
  filter->ramp_step = 1.0;
  filter->smoothed_brightness = DEFAULT_PROP_TARGET_BRIGHTNESS;
  filter->brightness_initialized = FALSE;

  /* Set in-place transform */
  gst_base_transform_set_in_place (GST_BASE_TRANSFORM (filter), TRUE);
  gst_base_transform_set_passthrough (GST_BASE_TRANSFORM (filter), TRUE);
}

static void
gst_intervalometer_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec)
{
  GstIntervalometer *filter = GST_INTERVALOMETER (object);

  switch (prop_id) {
    case PROP_ENABLED:
      filter->enabled = g_value_get_boolean (value);
      break;
    case PROP_TARGET_BRIGHTNESS:
      filter->target_brightness = g_value_get_double (value);
      break;
    case PROP_COMPENSATION:
      filter->compensation = g_value_get_double (value);
      break;
    case PROP_EXPOSURE_MIN:
      filter->exposure_min = g_value_get_double (value);
      break;
    case PROP_EXPOSURE_MAX:
      filter->exposure_max = g_value_get_double (value);
      break;
    case PROP_GAIN_MIN:
      filter->gain_min = g_value_get_int (value);
      break;
    case PROP_GAIN_MAX:
      filter->gain_max = g_value_get_int (value);
      break;
    case PROP_RAMP_RATE:
      filter->ramp_rate = g_value_get_enum (value);
      break;
    case PROP_LOG_FILE:
      g_free (filter->log_file);
      filter->log_file = g_value_dup_string (value);
      break;
    case PROP_CAMERA_ELEMENT:
      g_free (filter->camera_element_name);
      filter->camera_element_name = g_value_dup_string (value);
      /* Try to find camera element when name is set */
      if (filter->camera_element_name && strlen (filter->camera_element_name) > 0) {
        filter->camera_src = gst_intervalometer_find_camera_element (filter);
      }
      break;
    case PROP_UPDATE_INTERVAL:
      filter->update_interval = g_value_get_uint (value);
      break;
    case PROP_BRIGHTNESS_SMOOTHING:
      filter->brightness_smoothing = g_value_get_double (value);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static void
gst_intervalometer_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec)
{
  GstIntervalometer *filter = GST_INTERVALOMETER (object);

  switch (prop_id) {
    case PROP_ENABLED:
      g_value_set_boolean (value, filter->enabled);
      break;
    case PROP_TARGET_BRIGHTNESS:
      g_value_set_double (value, filter->target_brightness);
      break;
    case PROP_COMPENSATION:
      g_value_set_double (value, filter->compensation);
      break;
    case PROP_EXPOSURE_MIN:
      g_value_set_double (value, filter->exposure_min);
      break;
    case PROP_EXPOSURE_MAX:
      g_value_set_double (value, filter->exposure_max);
      break;
    case PROP_GAIN_MIN:
      g_value_set_int (value, filter->gain_min);
      break;
    case PROP_GAIN_MAX:
      g_value_set_int (value, filter->gain_max);
      break;
    case PROP_RAMP_RATE:
      g_value_set_enum (value, filter->ramp_rate);
      break;
    case PROP_LOG_FILE:
      g_value_set_string (value, filter->log_file);
      break;
    case PROP_CAMERA_ELEMENT:
      g_value_set_string (value, filter->camera_element_name);
      break;
    case PROP_UPDATE_INTERVAL:
      g_value_set_uint (value, filter->update_interval);
      break;
    case PROP_BRIGHTNESS_SMOOTHING:
      g_value_set_double (value, filter->brightness_smoothing);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static void
gst_intervalometer_dispose (GObject * object)
{
  GstIntervalometer *filter = GST_INTERVALOMETER (object);

  if (filter->camera_src) {
    gst_object_unref (filter->camera_src);
    filter->camera_src = NULL;
  }

  G_OBJECT_CLASS (parent_class)->dispose (object);
}

static void
gst_intervalometer_finalize (GObject * object)
{
  GstIntervalometer *filter = GST_INTERVALOMETER (object);

  g_free (filter->log_file);
  g_free (filter->camera_element_name);

  if (filter->log_fp) {
    fclose (filter->log_fp);
    filter->log_fp = NULL;
  }

  G_OBJECT_CLASS (parent_class)->finalize (object);
}

static gboolean
gst_intervalometer_start (GstBaseTransform * trans)
{
  GstIntervalometer *filter = GST_INTERVALOMETER (trans);

  GST_DEBUG_OBJECT (filter, "start");

  filter->frame_count = 0;
  filter->start_time = gst_clock_get_time (gst_system_clock_obtain ());

  /* Open log file if specified */
  if (filter->log_file && strlen (filter->log_file) > 0) {
    filter->log_fp = fopen (filter->log_file, "w");
    if (!filter->log_fp) {
      GST_WARNING_OBJECT (filter, "Failed to open log file: %s", filter->log_file);
    } else {
      filter->log_header_written = FALSE;
    }
  }

  /* Find camera element if name was provided */
  if (filter->camera_element_name && strlen (filter->camera_element_name) > 0) {
    filter->camera_src = gst_intervalometer_find_camera_element (filter);
    if (!filter->camera_src) {
      GST_WARNING_OBJECT (filter, "Could not find camera element: %s",
          filter->camera_element_name);
    } else {
      GST_INFO_OBJECT (filter, "Found camera element, will query capabilities when camera is ready");
    }
  }

  gst_intervalometer_reset (filter);

  return TRUE;
}

static gboolean
gst_intervalometer_stop (GstBaseTransform * trans)
{
  GstIntervalometer *filter = GST_INTERVALOMETER (trans);

  GST_DEBUG_OBJECT (filter, "stop");

  if (filter->log_fp) {
    fclose (filter->log_fp);
    filter->log_fp = NULL;
  }

  if (filter->camera_src) {
    gst_object_unref (filter->camera_src);
    filter->camera_src = NULL;
  }

  return TRUE;
}

static gboolean
gst_intervalometer_set_caps (GstBaseTransform * trans, GstCaps * incaps,
    GstCaps * outcaps)
{
  GstIntervalometer *filter = GST_INTERVALOMETER (trans);

  if (!gst_video_info_from_caps (&filter->video_info, incaps)) {
    GST_ERROR_OBJECT (filter, "Failed to parse caps");
    return FALSE;
  }

  filter->video_info_valid = TRUE;

  GST_DEBUG_OBJECT (filter, "Set caps: %" GST_PTR_FORMAT, incaps);

  return TRUE;
}

static GstFlowReturn
gst_intervalometer_transform_ip (GstBaseTransform * trans, GstBuffer * buf)
{
  GstIntervalometer *filter = GST_INTERVALOMETER (trans);
  gdouble brightness;
  GstClockTime now;
  gboolean should_update = FALSE;

  if (!filter->enabled || !filter->video_info_valid) {
    return GST_FLOW_OK;
  }

  /* Query camera capabilities on first frame if not done yet */
  if (filter->camera_src && !filter->hCam && filter->exposure_min == 0.0) {
    if (gst_intervalometer_query_camera_capabilities (filter)) {
      GST_INFO_OBJECT (filter, "Successfully queried camera capabilities on first frame");
      gst_intervalometer_reset (filter);  /* Re-read current settings with proper handle */
    }
  }

  /* Get current time */
  now = gst_clock_get_time (gst_system_clock_obtain ());

  /* Check if we should update based on interval */
  if (filter->update_interval == 0) {
    /* Update every frame */
    should_update = TRUE;
  } else if (filter->last_update_time == GST_CLOCK_TIME_NONE) {
    /* First update */
    should_update = TRUE;
  } else {
    /* Check if enough time has passed */
    GstClockTime elapsed = GST_CLOCK_DIFF (filter->last_update_time, now);
    GstClockTime interval_ns = filter->update_interval * GST_MSECOND;
    
    if (elapsed >= interval_ns) {
      should_update = TRUE;
    }
  }

  /* Always calculate brightness for logging */
  brightness = gst_intervalometer_calculate_brightness (filter, buf);

  /* Apply exponential moving average for brightness smoothing */
  if (!filter->brightness_initialized) {
    /* Initialize smoothed brightness on first frame */
    filter->smoothed_brightness = brightness;
    filter->brightness_initialized = TRUE;
  } else {
    /* Exponential moving average: new_value = alpha * current + (1-alpha) * old */
    filter->smoothed_brightness = (filter->brightness_smoothing * brightness) +
        ((1.0 - filter->brightness_smoothing) * filter->smoothed_brightness);
  }

  /* Only update camera settings at the specified interval */
  if (should_update) {
    /* Use smoothed brightness to filter out transient object movements */
    gst_intervalometer_update_camera_settings (filter, filter->smoothed_brightness);
    filter->last_update_time = now;
  }

  /* Write to log file if enabled */
  if (filter->log_fp) {
    gst_intervalometer_write_log (filter, brightness);
  }

  filter->frame_count++;

  return GST_FLOW_OK;
}

static void
gst_intervalometer_reset (GstIntervalometer * filter)
{
  /* Query current camera settings using IDS uEye SDK */
  if (filter->camera_src && filter->hCam) {
    /* Get current exposure using IDS SDK */
    double current_exp = 0.0;
    INT ret = is_Exposure (filter->hCam, IS_EXPOSURE_CMD_GET_EXPOSURE,
        &current_exp, sizeof(double));
    if (ret == IS_SUCCESS) {
      filter->current_exposure = current_exp;
      filter->target_exposure = current_exp;
      GST_INFO_OBJECT (filter, "Queried current exposure from camera: %.3f ms",
          current_exp);
    } else {
      GST_WARNING_OBJECT (filter, "Failed to query exposure from camera (error %d), using min",
          ret);
      filter->current_exposure = filter->exposure_min;
      filter->target_exposure = filter->exposure_min;
    }

    /* Get current gain using GObject (gain doesn't have SDK query function) */
    g_object_get (filter->camera_src, "gain", &filter->current_gain, NULL);
    filter->target_gain = filter->current_gain;
    GST_INFO_OBJECT (filter, "Queried current gain: %d", filter->current_gain);
  } else {
    /* Fallback to min values if camera not available */
    filter->current_exposure = filter->exposure_min;
    filter->current_gain = filter->gain_min;
    filter->target_exposure = filter->exposure_min;
    filter->target_gain = filter->gain_min;
  }
  filter->frame_count = 0;
}

static gdouble
gst_intervalometer_calculate_brightness (GstIntervalometer * filter,
    GstBuffer * buf)
{
  GstMapInfo map;
  gdouble sum = 0.0;
  guint64 pixel_count = 0;
  guint i;

  if (!gst_buffer_map (buf, &map, GST_MAP_READ)) {
    GST_WARNING_OBJECT (filter, "Failed to map buffer");
    return filter->target_brightness;
  }

  /* Calculate average brightness based on format */
  switch (GST_VIDEO_INFO_FORMAT (&filter->video_info)) {
    case GST_VIDEO_FORMAT_GRAY8:
    {
      guint8 *data = map.data;
      pixel_count = map.size;
      for (i = 0; i < pixel_count; i++) {
        sum += data[i];
      }
      break;
    }
    case GST_VIDEO_FORMAT_GRAY16_LE:
    case GST_VIDEO_FORMAT_GRAY16_BE:
    {
      guint16 *data = (guint16 *) map.data;
      pixel_count = map.size / 2;
      for (i = 0; i < pixel_count; i++) {
        sum += data[i] / 256.0;  /* Scale 16-bit to 8-bit range */
      }
      break;
    }
    case GST_VIDEO_FORMAT_RGB:
    case GST_VIDEO_FORMAT_BGR:
    {
      /* Calculate luminance: Y = 0.299*R + 0.587*G + 0.114*B */
      guint8 *data = map.data;
      pixel_count = map.size / 3;
      for (i = 0; i < map.size; i += 3) {
        sum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
      }
      break;
    }
    case GST_VIDEO_FORMAT_BGRA:
    {
      guint8 *data = map.data;
      pixel_count = map.size / 4;
      for (i = 0; i < map.size; i += 4) {
        sum += 0.299 * data[i + 2] + 0.587 * data[i + 1] + 0.114 * data[i];
      }
      break;
    }
    default:
      GST_WARNING_OBJECT (filter, "Unsupported video format");
      gst_buffer_unmap (buf, &map);
      return filter->target_brightness;
  }

  gst_buffer_unmap (buf, &map);

  if (pixel_count == 0) {
    return filter->target_brightness;
  }

  return sum / pixel_count;
}

static void
gst_intervalometer_update_camera_settings (GstIntervalometer * filter,
    gdouble brightness)
{
  gdouble error, adjusted_target, exposure_range, gain_range;
  gdouble ramp_multiplier;

  if (!filter->camera_src) {
    return;
  }

  /* Calculate brightness error with compensation */
  error = (filter->target_brightness - brightness) *
      pow (2.0, filter->compensation);

  /* Adjust target brightness based on error */
  adjusted_target = filter->target_brightness + error;

  /* Get ramp multiplier */
  ramp_multiplier = ramp_rate_multipliers[filter->ramp_rate];

  /* Calculate exposure and gain ranges */
  exposure_range = filter->exposure_max - filter->exposure_min;
  gain_range = filter->gain_max - filter->gain_min;

  /* Determine target exposure and gain using YASS-like algorithm */
  if (brightness > adjusted_target) {
    /* Too bright - decrease exposure first, then gain */
    if (filter->current_exposure > filter->exposure_min) {
      filter->target_exposure = filter->current_exposure -
          (exposure_range * 0.01 * ramp_multiplier);
      filter->target_exposure = MAX (filter->target_exposure, filter->exposure_min);
    } else if (filter->current_gain > filter->gain_min) {
      filter->target_gain = filter->current_gain - (gint) (ramp_multiplier);
      filter->target_gain = MAX (filter->target_gain, filter->gain_min);
    }
  } else {
    /* Too dark - increase exposure first up to max, then increase gain */
    if (filter->current_exposure < filter->exposure_max) {
      filter->target_exposure = filter->current_exposure +
          (exposure_range * 0.01 * ramp_multiplier);
      filter->target_exposure = MIN (filter->target_exposure, filter->exposure_max);
    } else if (filter->current_gain < filter->gain_max) {
      filter->target_gain = filter->current_gain + (gint) (ramp_multiplier);
      filter->target_gain = MIN (filter->target_gain, filter->gain_max);
    }
  }

  /* Apply smooth ramping using ramp_step */
  gdouble exp_delta = filter->target_exposure - filter->current_exposure;
  gdouble gain_delta = filter->target_gain - filter->current_gain;

  /* Calculate ramp step based on ramp rate (percentage of delta per update) */
  filter->ramp_step = 0.1 * ramp_multiplier; /* 10% base rate, scaled by ramp setting */

  /* Ramp exposure smoothly towards target */
  if (fabs (exp_delta) > 0.001) {
    gdouble old_exposure = filter->current_exposure;
    filter->current_exposure += exp_delta * filter->ramp_step;
    g_object_set (filter->camera_src, "exposure", filter->current_exposure, NULL);
    GST_DEBUG_OBJECT (filter, "Ramping exposure: %.3f -> %.3f (target %.3f, step %.1f%%)",
        old_exposure, filter->current_exposure, filter->target_exposure,
        filter->ramp_step * 100);
  }

  /* Ramp gain smoothly towards target */
  if (gain_delta != 0) {
    gdouble gain_step = gain_delta * filter->ramp_step;
    /* Ensure minimum step of 1 for gain (integer values) */
    if (fabs (gain_step) < 1.0) {
      gain_step = (gain_delta > 0) ? 1.0 : -1.0;
    }
    gint old_gain = filter->current_gain;
    filter->current_gain += (gint) gain_step;
    g_object_set (filter->camera_src, "gain", filter->current_gain, NULL);
    GST_DEBUG_OBJECT (filter, "Ramping gain: %d -> %d (target %d)",
        old_gain, filter->current_gain, filter->target_gain);
  }
}

static void
gst_intervalometer_write_log (GstIntervalometer * filter, gdouble brightness)
{
  if (!filter->log_fp) {
    return;
  }

  /* Write CSV header on first frame */
  if (!filter->log_header_written) {
    fprintf (filter->log_fp,
        "Frame,Time_s,Brightness,Exposure_ms,Gain,Target_Brightness\n");
    filter->log_header_written = TRUE;
  }

  /* Calculate elapsed time */
  GstClockTime now = gst_clock_get_time (gst_system_clock_obtain ());
  gdouble elapsed = (now - filter->start_time) / 1000000000.0;

  /* Write data row */
  fprintf (filter->log_fp, "%llu,%.3f,%.2f,%.3f,%d,%.2f\n",
      (unsigned long long) filter->frame_count,
      elapsed,
      brightness,
      filter->current_exposure,
      filter->current_gain,
      filter->target_brightness);

  fflush (filter->log_fp);
}

static GstElement *
gst_intervalometer_find_camera_element (GstIntervalometer * filter)
{
  GstElement *pipeline, *element = NULL;
  GstBin *bin;

  /* Get pipeline */
  pipeline = GST_ELEMENT (gst_element_get_parent (GST_ELEMENT (filter)));
  if (!pipeline) {
    GST_WARNING_OBJECT (filter, "Not in a pipeline");
    return NULL;
  }

  /* Search for element by name */
  if (GST_IS_BIN (pipeline)) {
    bin = GST_BIN (pipeline);
    element = gst_bin_get_by_name (bin, filter->camera_element_name);
  }

  gst_object_unref (pipeline);

  if (element) {
    GST_INFO_OBJECT (filter, "Found camera element: %s",
        filter->camera_element_name);
  } else {
    GST_WARNING_OBJECT (filter, "Could not find camera element: %s",
        filter->camera_element_name);
  }

  return element;
}

static gboolean
gst_intervalometer_query_camera_capabilities (GstIntervalometer * filter)
{
  if (!filter->camera_src) {
    GST_WARNING_OBJECT (filter, "No camera element to query");
    return FALSE;
  }

  /* Get the IDS uEye camera handle from idsueyesrc element */
  gpointer hcam_ptr = NULL;
  g_object_get (filter->camera_src, "hcam", &hcam_ptr, NULL);
  if (!hcam_ptr) {
    GST_WARNING_OBJECT (filter, "Failed to get camera handle from idsueyesrc");
    return FALSE;
  }
  
  /* Convert pointer back to HIDS (DWORD) */
  filter->hCam = (HIDS)(uintptr_t)hcam_ptr;
  GST_INFO_OBJECT (filter, "Got IDS uEye camera handle: 0x%x", filter->hCam);

  /* Query exposure limits using IDS uEye SDK if not manually set */
  if (filter->exposure_min == 0.0 || filter->exposure_max == 0.0) {
    double exposure_range[3];  /* [min, max, increment] */
    INT ret = is_Exposure (filter->hCam, IS_EXPOSURE_CMD_GET_EXPOSURE_RANGE,
        exposure_range, sizeof(exposure_range));
    
    if (ret == IS_SUCCESS) {
      if (filter->exposure_min == 0.0) {
        filter->exposure_min = exposure_range[0];
        GST_INFO_OBJECT (filter, "Queried exposure_min: %.3f ms", filter->exposure_min);
      }
      if (filter->exposure_max == 0.0) {
        filter->exposure_max = exposure_range[1];
        GST_INFO_OBJECT (filter, "Queried exposure_max: %.3f ms", filter->exposure_max);
      }
      GST_INFO_OBJECT (filter, "Exposure range increment: %.3f ms", exposure_range[2]);
    } else {
      GST_WARNING_OBJECT (filter, "Failed to query exposure range from IDS SDK (error %d)", ret);
      return FALSE;
    }
  }

  /* Query gain limits from GObject properties (IDS SDK doesn't have dedicated gain range query) */
  if (filter->gain_min == 0 || filter->gain_max == 0) {
    GParamSpec *pspec;
    GObjectClass *cam_class = G_OBJECT_GET_CLASS (filter->camera_src);
    
    pspec = g_object_class_find_property (cam_class, "gain");
    if (pspec && G_IS_PARAM_SPEC_INT (pspec)) {
      GParamSpecInt *int_spec = G_PARAM_SPEC_INT (pspec);
      if (filter->gain_min == 0) {
        filter->gain_min = int_spec->minimum;
        GST_INFO_OBJECT (filter, "Queried gain_min: %d", filter->gain_min);
      }
      if (filter->gain_max == 0) {
        filter->gain_max = int_spec->maximum;
        GST_INFO_OBJECT (filter, "Queried gain_max: %d", filter->gain_max);
      }
    } else {
      GST_WARNING_OBJECT (filter, "Could not query gain limits from camera");
      return FALSE;
    }
  }

  GST_INFO_OBJECT (filter, "Camera capabilities: exposure=[%.3f, %.3f] ms, gain=[%d, %d]",
      filter->exposure_min, filter->exposure_max, filter->gain_min, filter->gain_max);

  return TRUE;
}

static gboolean
plugin_init (GstPlugin * plugin)
{
  return gst_element_register (plugin, "intervalometer", GST_RANK_NONE,
      GST_TYPE_INTERVALOMETER);
}

GST_PLUGIN_DEFINE (GST_VERSION_MAJOR,
    GST_VERSION_MINOR,
    intervalometer,
    "Automatic exposure control for IDS uEye cameras",
    plugin_init, GST_PACKAGE_VERSION, GST_PACKAGE_LICENSE, GST_PACKAGE_NAME,
    GST_PACKAGE_ORIGIN)