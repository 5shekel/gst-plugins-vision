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
  PROP_CAMERA_ELEMENT
};

#define DEFAULT_PROP_ENABLED TRUE
#define DEFAULT_PROP_TARGET_BRIGHTNESS 128.0
#define DEFAULT_PROP_COMPENSATION 0.0
#define DEFAULT_PROP_EXPOSURE_MIN 0.85
#define DEFAULT_PROP_EXPOSURE_MAX 1.24
#define DEFAULT_PROP_GAIN_MIN 0
#define DEFAULT_PROP_GAIN_MAX 52
#define DEFAULT_PROP_RAMP_RATE RAMP_RATE_MEDIUM
#define DEFAULT_PROP_LOG_FILE ""
#define DEFAULT_PROP_CAMERA_ELEMENT ""

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
          "Minimum exposure time in milliseconds", 0.01, 1000.0,
          DEFAULT_PROP_EXPOSURE_MIN,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_EXPOSURE_MAX,
      g_param_spec_double ("exposure-max", "Maximum Exposure",
          "Maximum exposure time in milliseconds", 0.01, 1000.0,
          DEFAULT_PROP_EXPOSURE_MAX,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_GAIN_MIN,
      g_param_spec_int ("gain-min", "Minimum Gain",
          "Minimum gain value", 0, 100, DEFAULT_PROP_GAIN_MIN,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_GAIN_MAX,
      g_param_spec_int ("gain-max", "Maximum Gain",
          "Maximum gain value", 0, 100, DEFAULT_PROP_GAIN_MAX,
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

  /* Initialize internal state */
  filter->camera_src = NULL;
  filter->current_exposure = DEFAULT_PROP_EXPOSURE_MIN;
  filter->current_gain = DEFAULT_PROP_GAIN_MIN;
  filter->target_exposure = DEFAULT_PROP_EXPOSURE_MIN;
  filter->target_gain = DEFAULT_PROP_GAIN_MIN;
  filter->frame_count = 0;
  filter->start_time = GST_CLOCK_TIME_NONE;
  filter->log_fp = NULL;
  filter->log_header_written = FALSE;
  filter->video_info_valid = FALSE;
  filter->ramp_step = 1.0;

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

  if (!filter->enabled || !filter->video_info_valid) {
    return GST_FLOW_OK;
  }

  /* Calculate brightness from current frame */
  brightness = gst_intervalometer_calculate_brightness (filter, buf);

  /* Update camera settings based on brightness */
  gst_intervalometer_update_camera_settings (filter, brightness);

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
  filter->current_exposure = filter->exposure_min;
  filter->current_gain = filter->gain_min;
  filter->target_exposure = filter->exposure_min;
  filter->target_gain = filter->gain_min;
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

  /* Smooth ramping towards target */
  if (fabs (filter->current_exposure - filter->target_exposure) > 0.001) {
    filter->current_exposure = filter->target_exposure;
    g_object_set (filter->camera_src, "exposure", filter->current_exposure, NULL);
    GST_DEBUG_OBJECT (filter, "Set exposure to %.3f ms", filter->current_exposure);
  }

  if (filter->current_gain != filter->target_gain) {
    filter->current_gain = filter->target_gain;
    g_object_set (filter->camera_src, "gain", filter->current_gain, NULL);
    GST_DEBUG_OBJECT (filter, "Set gain to %d", filter->current_gain);
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