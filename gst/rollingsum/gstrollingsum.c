/* GStreamer
 * Copyright (C) 2024 <your-name@your-email.com>
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
 * SECTION:element-rollingsum
 *
 * Drops frames based on rolling mean analysis of a single column.
 * Inspired by cli.py detection algorithm, simplified for real-time streaming.
 *
 * <refsect2>
 * <title>Example launch line</title>
 * |[
 * gst-launch-1.0 idsueyesrc config-file=config.ini ! rollingsum window-size=1000 column-index=1 threshold=0.5 ! autovideosink
 * ]|
 * </refsect2>
 */

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include "gstrollingsum.h"
#include <string.h>
#include <math.h>

enum
{
  PROP_0,
  PROP_WINDOW_SIZE,
  PROP_COLUMN_INDEX,
  PROP_STRIDE,
  PROP_THRESHOLD,
  PROP_LAST
};

#define DEFAULT_PROP_WINDOW_SIZE 1000
#define DEFAULT_PROP_COLUMN_INDEX 1
#define DEFAULT_PROP_STRIDE 1
#define DEFAULT_PROP_THRESHOLD 0.5

/* Supported video formats */
#define SUPPORTED_CAPS \
  GST_VIDEO_CAPS_MAKE("{ GRAY8, GRAY16_LE, GRAY16_BE }") ";" \
  "video/x-bayer, format=(string){bggr,grbg,gbrg,rggb}"

static GstStaticPadTemplate gst_rolling_sum_sink_template =
GST_STATIC_PAD_TEMPLATE ("sink",
    GST_PAD_SINK,
    GST_PAD_ALWAYS,
    GST_STATIC_CAPS (SUPPORTED_CAPS)
    );

static GstStaticPadTemplate gst_rolling_sum_src_template =
GST_STATIC_PAD_TEMPLATE ("src",
    GST_PAD_SRC,
    GST_PAD_ALWAYS,
    GST_STATIC_CAPS (SUPPORTED_CAPS)
    );

/* GObject vmethod declarations */
static void gst_rolling_sum_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec);
static void gst_rolling_sum_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec);
static void gst_rolling_sum_dispose (GObject * object);

/* GstBaseTransform vmethod declarations */
static gboolean gst_rolling_sum_set_caps (GstBaseTransform * trans,
    GstCaps * incaps, GstCaps * outcaps);
static GstFlowReturn gst_rolling_sum_transform_ip (GstBaseTransform * trans,
    GstBuffer * buf);

/* GstRollingSum method declarations */
static void gst_rolling_sum_reset (GstRollingSum * filter);
static gdouble gst_rolling_sum_extract_column_mean (GstRollingSum * filter,
    GstBuffer * buf);

/* setup debug */
GST_DEBUG_CATEGORY_STATIC (rolling_sum_debug);
#define GST_CAT_DEFAULT rolling_sum_debug

G_DEFINE_TYPE (GstRollingSum, gst_rolling_sum, GST_TYPE_BASE_TRANSFORM);

/************************************************************************/
/* GObject vmethod implementations                                      */
/************************************************************************/

static void
gst_rolling_sum_dispose (GObject * object)
{
  GstRollingSum *filter = GST_ROLLING_SUM (object);

  GST_DEBUG ("dispose");

  gst_rolling_sum_reset (filter);

  /* chain up to the parent class */
  G_OBJECT_CLASS (gst_rolling_sum_parent_class)->dispose (object);
}

static void
gst_rolling_sum_class_init (GstRollingSumClass * klass)
{
  GObjectClass *gobject_class = G_OBJECT_CLASS (klass);
  GstElementClass *gstelement_class = GST_ELEMENT_CLASS (klass);
  GstBaseTransformClass *gstbasetransform_class =
      GST_BASE_TRANSFORM_CLASS (klass);

  GST_DEBUG_CATEGORY_INIT (rolling_sum_debug, "rollingsum", 0,
      "Rolling Sum Filter");

  GST_DEBUG ("class init");

  /* Register GObject vmethods */
  gobject_class->dispose = GST_DEBUG_FUNCPTR (gst_rolling_sum_dispose);
  gobject_class->set_property = GST_DEBUG_FUNCPTR (gst_rolling_sum_set_property);
  gobject_class->get_property = GST_DEBUG_FUNCPTR (gst_rolling_sum_get_property);

  /* Install GObject properties */
  g_object_class_install_property (gobject_class, PROP_WINDOW_SIZE,
      g_param_spec_int ("window-size", "Window Size",
          "Number of frames in rolling window", 1, 100000,
          DEFAULT_PROP_WINDOW_SIZE,
          G_PARAM_STATIC_STRINGS | G_PARAM_READWRITE |
          GST_PARAM_MUTABLE_PLAYING));

  g_object_class_install_property (gobject_class, PROP_COLUMN_INDEX,
      g_param_spec_int ("column-index", "Column Index",
          "Which vertical column to analyze (0-based)", 0, G_MAXINT,
          DEFAULT_PROP_COLUMN_INDEX,
          G_PARAM_STATIC_STRINGS | G_PARAM_READWRITE |
          GST_PARAM_MUTABLE_PLAYING));

  g_object_class_install_property (gobject_class, PROP_STRIDE,
      g_param_spec_int ("stride", "Row Stride",
          "Row sampling stride (1 = every row)", 1, G_MAXINT,
          DEFAULT_PROP_STRIDE,
          G_PARAM_STATIC_STRINGS | G_PARAM_READWRITE |
          GST_PARAM_MUTABLE_PLAYING));

  g_object_class_install_property (gobject_class, PROP_THRESHOLD,
      g_param_spec_double ("threshold", "Threshold",
          "Normalized deviation threshold for dropping frames", 0.0, 1.0,
          DEFAULT_PROP_THRESHOLD,
          G_PARAM_STATIC_STRINGS | G_PARAM_READWRITE |
          GST_PARAM_MUTABLE_PLAYING));

  gst_element_class_add_pad_template (gstelement_class,
      gst_static_pad_template_get (&gst_rolling_sum_sink_template));
  gst_element_class_add_pad_template (gstelement_class,
      gst_static_pad_template_get (&gst_rolling_sum_src_template));

  gst_element_class_set_static_metadata (gstelement_class,
      "Rolling sum filter", "Filter/Effect/Video",
      "Drops frames based on rolling mean analysis of a single column",
      "Your Name <your-email@example.com>");

  /* Register GstBaseTransform vmethods */
  gstbasetransform_class->set_caps =
      GST_DEBUG_FUNCPTR (gst_rolling_sum_set_caps);
  gstbasetransform_class->transform_ip =
      GST_DEBUG_FUNCPTR (gst_rolling_sum_transform_ip);
}

static void
gst_rolling_sum_init (GstRollingSum * filter)
{
  GST_DEBUG_OBJECT (filter, "init class instance");

  filter->window_size = DEFAULT_PROP_WINDOW_SIZE;
  filter->column_index = DEFAULT_PROP_COLUMN_INDEX;
  filter->stride = DEFAULT_PROP_STRIDE;
  filter->threshold = DEFAULT_PROP_THRESHOLD;

  filter->ring_buffer = NULL;
  filter->ring_index = 0;
  filter->frame_count = 0;
  filter->rolling_mean = 0.0;
  filter->rolling_sum = 0.0;
  filter->info_set = FALSE;

  gst_base_transform_set_in_place (GST_BASE_TRANSFORM (filter), TRUE);

  gst_rolling_sum_reset (filter);
}

static void
gst_rolling_sum_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec)
{
  GstRollingSum *filter = GST_ROLLING_SUM (object);

  GST_DEBUG_OBJECT (filter, "setting property %s", pspec->name);

  switch (prop_id) {
    case PROP_WINDOW_SIZE:
    {
      gint new_size = g_value_get_int (value);
      if (new_size != filter->window_size) {
        filter->window_size = new_size;
        /* Reallocate ring buffer */
        gst_rolling_sum_reset (filter);
      }
      break;
    }
    case PROP_COLUMN_INDEX:
      filter->column_index = g_value_get_int (value);
      break;
    case PROP_STRIDE:
      filter->stride = g_value_get_int (value);
      break;
    case PROP_THRESHOLD:
      filter->threshold = g_value_get_double (value);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static void
gst_rolling_sum_get_property (GObject * object, guint prop_id, GValue * value,
    GParamSpec * pspec)
{
  GstRollingSum *filter = GST_ROLLING_SUM (object);

  GST_DEBUG_OBJECT (filter, "getting property %s", pspec->name);

  switch (prop_id) {
    case PROP_WINDOW_SIZE:
      g_value_set_int (value, filter->window_size);
      break;
    case PROP_COLUMN_INDEX:
      g_value_set_int (value, filter->column_index);
      break;
    case PROP_STRIDE:
      g_value_set_int (value, filter->stride);
      break;
    case PROP_THRESHOLD:
      g_value_set_double (value, filter->threshold);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static gboolean
gst_rolling_sum_set_caps (GstBaseTransform * trans, GstCaps * incaps,
    GstCaps * outcaps)
{
  GstRollingSum *filter = GST_ROLLING_SUM (trans);

  GST_DEBUG_OBJECT (filter, "set_caps");

  if (!gst_video_info_from_caps (&filter->video_info, incaps)) {
    GST_ERROR_OBJECT (filter, "Failed to parse caps");
    return FALSE;
  }

  filter->info_set = TRUE;

  GST_DEBUG_OBJECT (filter, "Video format: %s, %dx%d",
      gst_video_format_to_string (GST_VIDEO_INFO_FORMAT (&filter->video_info)),
      GST_VIDEO_INFO_WIDTH (&filter->video_info),
      GST_VIDEO_INFO_HEIGHT (&filter->video_info));

  return TRUE;
}

static gdouble
gst_rolling_sum_extract_column_mean (GstRollingSum * filter, GstBuffer * buf)
{
  GstMapInfo map;
  gdouble sum = 0.0;
  gint count = 0;
  gint width, height, stride_bytes;
  gint row, col_offset;
  guint8 *data;
  GstVideoFormat format;

  if (!filter->info_set) {
    GST_WARNING_OBJECT (filter, "Video info not set yet");
    return 0.0;
  }

  if (!gst_buffer_map (buf, &map, GST_MAP_READ)) {
    GST_ERROR_OBJECT (filter, "Failed to map buffer");
    return 0.0;
  }

  data = map.data;
  width = GST_VIDEO_INFO_WIDTH (&filter->video_info);
  height = GST_VIDEO_INFO_HEIGHT (&filter->video_info);
  stride_bytes = GST_VIDEO_INFO_PLANE_STRIDE (&filter->video_info, 0);
  format = GST_VIDEO_INFO_FORMAT (&filter->video_info);

  /* Check column index is valid */
  if (filter->column_index >= width) {
    GST_WARNING_OBJECT (filter, "Column index %d >= width %d, using column 0",
        filter->column_index, width);
    filter->column_index = 0;
  }

  /* Calculate column offset based on format */
  if (format == GST_VIDEO_FORMAT_GRAY8) {
    col_offset = filter->column_index;
    
    /* Sum column values with stride */
    for (row = 0; row < height; row += filter->stride) {
      sum += data[row * stride_bytes + col_offset];
      count++;
    }
  } else if (format == GST_VIDEO_FORMAT_GRAY16_LE ||
             format == GST_VIDEO_FORMAT_GRAY16_BE) {
    col_offset = filter->column_index * 2;
    
    /* Sum column values with stride */
    for (row = 0; row < height; row += filter->stride) {
      guint16 pixel_value;
      guint8 *pixel_ptr = &data[row * stride_bytes + col_offset];
      
      if (format == GST_VIDEO_FORMAT_GRAY16_LE) {
        pixel_value = pixel_ptr[0] | (pixel_ptr[1] << 8);
      } else {
        pixel_value = (pixel_ptr[0] << 8) | pixel_ptr[1];
      }
      
      sum += pixel_value;
      count++;
    }
  } else {
    /* For Bayer formats, treat as GRAY8 */
    col_offset = filter->column_index;
    
    for (row = 0; row < height; row += filter->stride) {
      sum += data[row * stride_bytes + col_offset];
      count++;
    }
  }

  gst_buffer_unmap (buf, &map);

  return count > 0 ? sum / count : 0.0;
}

static GstFlowReturn
gst_rolling_sum_transform_ip (GstBaseTransform * trans, GstBuffer * buf)
{
  GstRollingSum *filter = GST_ROLLING_SUM (trans);
  gdouble frame_mean, deviation, old_value;
  gint effective_window_size;

  /* Extract column mean from current frame */
  frame_mean = gst_rolling_sum_extract_column_mean (filter, buf);

  /* Store in ring buffer */
  old_value = filter->ring_buffer[filter->ring_index];
  filter->ring_buffer[filter->ring_index] = frame_mean;

  /* Update rolling sum efficiently */
  if (filter->frame_count < filter->window_size) {
    /* Still filling the buffer */
    filter->rolling_sum += frame_mean;
    filter->frame_count++;
    effective_window_size = filter->frame_count;
  } else {
    /* Buffer is full, replace old value */
    filter->rolling_sum = filter->rolling_sum - old_value + frame_mean;
    effective_window_size = filter->window_size;
  }

  /* Update rolling mean */
  filter->rolling_mean = filter->rolling_sum / effective_window_size;

  /* Calculate deviation */
  deviation = fabs(frame_mean - filter->rolling_mean);

  /* Normalize deviation (assuming 8-bit equivalent range) */
  gdouble normalized_deviation = deviation / 255.0;

  GST_LOG_OBJECT (filter,
      "Frame %d: mean=%.2f, rolling_mean=%.2f, deviation=%.2f (normalized=%.4f)",
      filter->frame_count, frame_mean, filter->rolling_mean, deviation,
      normalized_deviation);

  /* Advance ring buffer index */
  filter->ring_index = (filter->ring_index + 1) % filter->window_size;

  /* Decision: drop or pass frame */
  if (normalized_deviation > filter->threshold) {
    GST_DEBUG_OBJECT (filter,
        "Dropping frame %d: deviation %.4f > threshold %.4f",
        filter->frame_count, normalized_deviation, filter->threshold);
    return GST_BASE_TRANSFORM_FLOW_DROPPED;
  }

  return GST_FLOW_OK;
}

static void
gst_rolling_sum_reset (GstRollingSum * filter)
{
  GST_DEBUG_OBJECT (filter, "reset");

  /* Free old ring buffer if exists */
  if (filter->ring_buffer) {
    g_free (filter->ring_buffer);
  }

  /* Allocate new ring buffer */
  filter->ring_buffer = g_new0 (gdouble, filter->window_size);
  filter->ring_index = 0;
  filter->frame_count = 0;
  filter->rolling_mean = 0.0;
  filter->rolling_sum = 0.0;
}

static gboolean
plugin_init (GstPlugin * plugin)
{
  GST_DEBUG_CATEGORY_INIT (GST_CAT_DEFAULT, "rollingsum", 0, "rollingsum");

  GST_DEBUG ("plugin_init");

  GST_CAT_INFO (GST_CAT_DEFAULT, "registering rollingsum element");

  if (!gst_element_register (plugin, "rollingsum", GST_RANK_NONE,
          GST_TYPE_ROLLING_SUM)) {
    return FALSE;
  }

  return TRUE;
}

GST_PLUGIN_DEFINE (GST_VERSION_MAJOR,
    GST_VERSION_MINOR,
    rollingsum,
    "Filter that drops frames based on rolling mean analysis",
    plugin_init, GST_PACKAGE_VERSION, GST_PACKAGE_LICENSE, GST_PACKAGE_NAME,
    GST_PACKAGE_ORIGIN);