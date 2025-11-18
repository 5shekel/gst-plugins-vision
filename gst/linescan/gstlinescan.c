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
 * SECTION:element-linescan
 *
 * Line scan camera simulator that extracts one row or column of pixels
 * from each input frame and stacks them to create a line scan image.
 * 
 * Useful for analyzing fast-moving objects with high frame rate cameras
 * (typically 200-750 fps). The user sets the output width, and the height
 * is determined by the input resolution.
 *
 * <refsect2>
 * <title>Example launch line</title>
 * |[
 * gst-launch-1.0 videotestsrc ! linescan direction=horizontal line-index=100 output-size=800 ! videoconvert ! autovideosink
 * ]|
 * Extracts row 100 from each frame and creates an 800-pixel wide output
 * </refsect2>
 */

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include "gstlinescan.h"
#include <string.h>

GST_DEBUG_CATEGORY_STATIC (gst_linescan_debug);
#define GST_CAT_DEFAULT gst_linescan_debug

/* Signals */
enum
{
  SIGNAL_ROLLOVER,
  LAST_SIGNAL
};

static guint gst_linescan_signals[LAST_SIGNAL] = { 0 };

/* Properties */
enum
{
  PROP_0,
  PROP_DIRECTION,
  PROP_LINE_INDEX,
  PROP_OUTPUT_SIZE
};

#define DEFAULT_PROP_DIRECTION GST_LINESCAN_DIRECTION_HORIZONTAL
#define DEFAULT_PROP_LINE_INDEX -1  /* -1 means middle of image */
#define DEFAULT_PROP_OUTPUT_SIZE 800

/* GStreamer boilerplate */
#define gst_linescan_parent_class parent_class
G_DEFINE_TYPE (GstLinescan, gst_linescan, GST_TYPE_BASE_TRANSFORM);

/* Define the enum type for direction */
#define GST_TYPE_LINESCAN_DIRECTION (gst_linescan_direction_get_type ())
static GType
gst_linescan_direction_get_type (void)
{
  static GType direction_type = 0;
  static const GEnumValue direction_values[] = {
    {GST_LINESCAN_DIRECTION_HORIZONTAL, "Extract horizontal row, stack vertically", "horizontal"},
    {GST_LINESCAN_DIRECTION_VERTICAL, "Extract vertical column, stack horizontally", "vertical"},
    {0, NULL, NULL}
  };

  if (!direction_type) {
    direction_type = g_enum_register_static ("GstLinescanDirection", direction_values);
  }
  return direction_type;
}

static GstStaticPadTemplate gst_linescan_sink_template =
GST_STATIC_PAD_TEMPLATE ("sink",
    GST_PAD_SINK,
    GST_PAD_ALWAYS,
    GST_STATIC_CAPS (GST_VIDEO_CAPS_MAKE ("{ GRAY8, GRAY16_LE, GRAY16_BE, RGB, BGR, BGRA, RGBx }"))
    );

static GstStaticPadTemplate gst_linescan_src_template =
GST_STATIC_PAD_TEMPLATE ("src",
    GST_PAD_SRC,
    GST_PAD_ALWAYS,
    GST_STATIC_CAPS (GST_VIDEO_CAPS_MAKE ("{ GRAY8, GRAY16_LE, GRAY16_BE, RGB, BGR, BGRA, RGBx }"))
    );

/* GObject vmethod declarations */
static void gst_linescan_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec);
static void gst_linescan_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec);
static void gst_linescan_finalize (GObject * object);

/* GstBaseTransform vmethod declarations */
static gboolean gst_linescan_start (GstBaseTransform * trans);
static gboolean gst_linescan_stop (GstBaseTransform * trans);
static gboolean gst_linescan_set_caps (GstBaseTransform * trans,
    GstCaps * incaps, GstCaps * outcaps);
static GstCaps * gst_linescan_transform_caps (GstBaseTransform * trans,
    GstPadDirection direction, GstCaps * caps, GstCaps * filter);
static GstCaps * gst_linescan_fixate_caps (GstBaseTransform * trans,
    GstPadDirection direction, GstCaps * caps, GstCaps * othercaps);
static gboolean gst_linescan_transform_size (GstBaseTransform * trans,
    GstPadDirection direction, GstCaps * caps, gsize size,
    GstCaps * othercaps, gsize * othersize);
static GstFlowReturn gst_linescan_transform (GstBaseTransform * trans,
    GstBuffer * inbuf, GstBuffer * outbuf);

/* Helper functions */
static void gst_linescan_reset (GstLinescan * filter);
static gboolean gst_linescan_allocate_buffer (GstLinescan * filter);

static void
gst_linescan_class_init (GstLinescanClass * klass)
{
  GObjectClass *gobject_class = G_OBJECT_CLASS (klass);
  GstElementClass *gstelement_class = GST_ELEMENT_CLASS (klass);
  GstBaseTransformClass *gstbasetransform_class =
      GST_BASE_TRANSFORM_CLASS (klass);

  GST_DEBUG_CATEGORY_INIT (gst_linescan_debug, "linescan", 0,
      "Line Scan Camera Simulator");

  /* Register GObject vmethods */
  gobject_class->set_property = gst_linescan_set_property;
  gobject_class->get_property = gst_linescan_get_property;
  gobject_class->finalize = gst_linescan_finalize;

  /* Install GObject properties */
  g_object_class_install_property (gobject_class, PROP_DIRECTION,
      g_param_spec_enum ("direction", "Direction",
          "Direction to extract line (horizontal=row, vertical=column)",
          GST_TYPE_LINESCAN_DIRECTION, DEFAULT_PROP_DIRECTION,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_LINE_INDEX,
      g_param_spec_int ("line-index", "Line Index",
          "Index of row/column to extract (-1 for middle)", -1, G_MAXINT,
          DEFAULT_PROP_LINE_INDEX,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  g_object_class_install_property (gobject_class, PROP_OUTPUT_SIZE,
      g_param_spec_int ("output-size", "Output Size",
          "Number of lines to accumulate (width for horizontal, height for vertical)",
          1, G_MAXINT, DEFAULT_PROP_OUTPUT_SIZE,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

  /* Install signals */
  /**
   * GstLinescan::rollover:
   * @linescan: the linescan instance
   * @buffer: the completed buffer at rollover
   *
   * Emitted when the buffer position wraps around to 0 after accumulating
   * output_size lines. The buffer contains a complete line scan image.
   * Applications can connect to this signal to save the image to disk.
   */
  gst_linescan_signals[SIGNAL_ROLLOVER] =
      g_signal_new ("rollover", G_TYPE_FROM_CLASS (klass),
      G_SIGNAL_RUN_LAST, G_STRUCT_OFFSET (GstLinescanClass, rollover),
      NULL, NULL, g_cclosure_marshal_VOID__BOXED,
      G_TYPE_NONE, 1, GST_TYPE_BUFFER);

  /* Set element metadata */
  gst_element_class_add_pad_template (gstelement_class,
      gst_static_pad_template_get (&gst_linescan_sink_template));
  gst_element_class_add_pad_template (gstelement_class,
      gst_static_pad_template_get (&gst_linescan_src_template));

  gst_element_class_set_static_metadata (gstelement_class,
      "Line Scan Camera", "Filter/Effect/Video",
      "Extracts single row/column from frames and builds line scan image",
      "FIXME <fixme@example.com>");

  /* Register GstBaseTransform vmethods */
  gstbasetransform_class->start = GST_DEBUG_FUNCPTR (gst_linescan_start);
  gstbasetransform_class->stop = GST_DEBUG_FUNCPTR (gst_linescan_stop);
  gstbasetransform_class->set_caps = GST_DEBUG_FUNCPTR (gst_linescan_set_caps);
  gstbasetransform_class->transform_caps = GST_DEBUG_FUNCPTR (gst_linescan_transform_caps);
  gstbasetransform_class->fixate_caps = GST_DEBUG_FUNCPTR (gst_linescan_fixate_caps);
  gstbasetransform_class->transform_size = GST_DEBUG_FUNCPTR (gst_linescan_transform_size);
  gstbasetransform_class->transform = GST_DEBUG_FUNCPTR (gst_linescan_transform);
}

static void
gst_linescan_init (GstLinescan * filter)
{
  /* Initialize properties */
  filter->direction = DEFAULT_PROP_DIRECTION;
  filter->line_index = DEFAULT_PROP_LINE_INDEX;
  filter->output_size = DEFAULT_PROP_OUTPUT_SIZE;

  /* Initialize internal state */
  filter->line_buffer = NULL;
  filter->buffer_position = 0;
  filter->line_size = 0;
  filter->actual_line_index = 0;
  filter->frame_count = 0;
  filter->video_info_valid = FALSE;
  filter->output_caps_set = FALSE;

  /* This is not an in-place transform */
  gst_base_transform_set_in_place (GST_BASE_TRANSFORM (filter), FALSE);
}

static void
gst_linescan_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec)
{
  GstLinescan *filter = GST_LINESCAN (object);

  switch (prop_id) {
    case PROP_DIRECTION:
      filter->direction = g_value_get_enum (value);
      gst_linescan_reset (filter);
      break;
    case PROP_LINE_INDEX:
      filter->line_index = g_value_get_int (value);
      break;
    case PROP_OUTPUT_SIZE:
      filter->output_size = g_value_get_int (value);
      gst_linescan_reset (filter);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static void
gst_linescan_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec)
{
  GstLinescan *filter = GST_LINESCAN (object);

  switch (prop_id) {
    case PROP_DIRECTION:
      g_value_set_enum (value, filter->direction);
      break;
    case PROP_LINE_INDEX:
      g_value_set_int (value, filter->line_index);
      break;
    case PROP_OUTPUT_SIZE:
      g_value_set_int (value, filter->output_size);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static void
gst_linescan_finalize (GObject * object)
{
  GstLinescan *filter = GST_LINESCAN (object);

  if (filter->line_buffer) {
    g_free (filter->line_buffer);
    filter->line_buffer = NULL;
  }

  G_OBJECT_CLASS (parent_class)->finalize (object);
}

static gboolean
gst_linescan_start (GstBaseTransform * trans)
{
  GstLinescan *filter = GST_LINESCAN (trans);

  GST_DEBUG_OBJECT (filter, "start");

  filter->frame_count = 0;
  filter->buffer_position = 0;

  return TRUE;
}

static gboolean
gst_linescan_stop (GstBaseTransform * trans)
{
  GstLinescan *filter = GST_LINESCAN (trans);

  GST_DEBUG_OBJECT (filter, "stop");

  if (filter->line_buffer) {
    g_free (filter->line_buffer);
    filter->line_buffer = NULL;
  }

  filter->video_info_valid = FALSE;
  filter->output_caps_set = FALSE;

  return TRUE;
}

static GstCaps *
gst_linescan_transform_caps (GstBaseTransform * trans,
    GstPadDirection direction, GstCaps * caps, GstCaps * filter_caps)
{
  GstLinescan *filter = GST_LINESCAN (trans);
  GstCaps *ret, *tmp;
  GstStructure *structure;
  gint i;

  GST_DEBUG_OBJECT (filter, "transform_caps (direction: %d) caps: %" GST_PTR_FORMAT, direction, caps);

  ret = gst_caps_new_empty ();

  for (i = 0; i < gst_caps_get_size (caps); i++) {
    structure = gst_caps_get_structure (caps, i);
    structure = gst_structure_copy (structure);
    
    if (direction == GST_PAD_SINK) {
      /* Transform sink caps to src caps (input -> output) */
      if (filter->direction == GST_LINESCAN_DIRECTION_HORIZONTAL) {
        /* Horizontal: extract row (width=input_width), stack vertically (height=output_size) */
        /* Width stays same as input, height becomes output_size */
        gst_structure_set (structure, "height", G_TYPE_INT, filter->output_size, NULL);
      } else {
        /* Vertical: extract column (height=input_height), stack horizontally (width=output_size) */
        /* Height stays same as input, width becomes output_size */
        gst_structure_set (structure, "width", G_TYPE_INT, filter->output_size, NULL);
      }
    } else {
      /* Transform src caps to sink caps (output -> input) */
      /* We need to be permissive here - input can be any size */
      if (filter->direction == GST_LINESCAN_DIRECTION_HORIZONTAL) {
        /* For horizontal: output height is fixed, so input height can vary */
        gst_structure_remove_field (structure, "height");
        gst_structure_set (structure, "height", GST_TYPE_INT_RANGE, 1, G_MAXINT, NULL);
      } else {
        /* For vertical: output width is fixed, so input width can vary */
        gst_structure_remove_field (structure, "width");
        gst_structure_set (structure, "width", GST_TYPE_INT_RANGE, 1, G_MAXINT, NULL);
      }
    }
    
    gst_caps_append_structure (ret, structure);
  }

  /* Apply filter if provided */
  if (filter_caps) {
    tmp = gst_caps_intersect_full (ret, filter_caps, GST_CAPS_INTERSECT_FIRST);
    gst_caps_unref (ret);
    ret = tmp;
  }

  GST_DEBUG_OBJECT (filter, "transformed caps: %" GST_PTR_FORMAT, ret);

  return ret;
}

static GstCaps *
gst_linescan_fixate_caps (GstBaseTransform * trans,
    GstPadDirection direction, GstCaps * caps, GstCaps * othercaps)
{
  GstLinescan *filter = GST_LINESCAN (trans);
  GstStructure *structure;
  GstCaps *result;

  GST_DEBUG_OBJECT (filter, "fixate_caps (direction: %d) caps: %" GST_PTR_FORMAT
      " othercaps: %" GST_PTR_FORMAT, direction, caps, othercaps);

  result = gst_caps_make_writable (othercaps);
  structure = gst_caps_get_structure (result, 0);

  if (direction == GST_PAD_SINK) {
    /* Fixating output caps based on input */
    GstVideoInfo info;
    
    if (gst_video_info_from_caps (&info, caps)) {
      if (filter->direction == GST_LINESCAN_DIRECTION_HORIZONTAL) {
        /* Horizontal: extract row, stack vertically */
        /* Width stays same as input, height becomes output_size */
        gst_structure_fixate_field_nearest_int (structure, "width",
            GST_VIDEO_INFO_WIDTH (&info));
        gst_structure_fixate_field_nearest_int (structure, "height", filter->output_size);
      } else {
        /* Vertical: extract column, stack horizontally */
        /* Width becomes output_size, height stays same as input */
        gst_structure_fixate_field_nearest_int (structure, "width", filter->output_size);
        gst_structure_fixate_field_nearest_int (structure, "height",
            GST_VIDEO_INFO_HEIGHT (&info));
      }
    }
  } else {
    /* Fixating input caps based on output - less constrained */
    /* Just fixate to something reasonable */
    gst_structure_fixate_field_nearest_int (structure, "width", 640);
    gst_structure_fixate_field_nearest_int (structure, "height", 480);
  }

  /* Fixate other fields using parent implementation */
  result = gst_caps_fixate (result);

  GST_DEBUG_OBJECT (filter, "fixated caps: %" GST_PTR_FORMAT, result);

  return result;
}

static gboolean
gst_linescan_transform_size (GstBaseTransform * trans,
    GstPadDirection direction, GstCaps * caps, gsize size,
    GstCaps * othercaps, gsize * othersize)
{
  GstLinescan *filter = GST_LINESCAN (trans);
  GstVideoInfo info;

  if (!gst_video_info_from_caps (&info, othercaps)) {
    GST_ERROR_OBJECT (filter, "Failed to parse othercaps");
    return FALSE;
  }

  *othersize = GST_VIDEO_INFO_SIZE (&info);

  GST_DEBUG_OBJECT (filter, "transform_size: %zu -> %zu", size, *othersize);

  return TRUE;
}

static gboolean
gst_linescan_set_caps (GstBaseTransform * trans, GstCaps * incaps,
    GstCaps * outcaps)
{
  GstLinescan *filter = GST_LINESCAN (trans);

  if (!gst_video_info_from_caps (&filter->video_info_in, incaps)) {
    GST_ERROR_OBJECT (filter, "Failed to parse input caps");
    return FALSE;
  }

  if (!gst_video_info_from_caps (&filter->video_info_out, outcaps)) {
    GST_ERROR_OBJECT (filter, "Failed to parse output caps");
    return FALSE;
  }

  filter->video_info_valid = TRUE;
  filter->output_caps_set = TRUE;

  /* Calculate actual line index if set to -1 (middle) */
  if (filter->line_index < 0) {
    if (filter->direction == GST_LINESCAN_DIRECTION_HORIZONTAL) {
      filter->actual_line_index = GST_VIDEO_INFO_HEIGHT (&filter->video_info_in) / 2;
    } else {
      filter->actual_line_index = GST_VIDEO_INFO_WIDTH (&filter->video_info_in) / 2;
    }
  } else {
    filter->actual_line_index = filter->line_index;
  }

  /* Allocate line buffer */
  if (!gst_linescan_allocate_buffer (filter)) {
    GST_ERROR_OBJECT (filter, "Failed to allocate line buffer");
    return FALSE;
  }

  GST_INFO_OBJECT (filter, "Set caps - Input: %dx%d, Output: %dx%d, Direction: %s, Line: %d",
      GST_VIDEO_INFO_WIDTH (&filter->video_info_in),
      GST_VIDEO_INFO_HEIGHT (&filter->video_info_in),
      GST_VIDEO_INFO_WIDTH (&filter->video_info_out),
      GST_VIDEO_INFO_HEIGHT (&filter->video_info_out),
      (filter->direction == GST_LINESCAN_DIRECTION_HORIZONTAL) ? "HORIZONTAL" : "VERTICAL",
      filter->actual_line_index);

  return TRUE;
}

static gboolean
gst_linescan_allocate_buffer (GstLinescan * filter)
{
  gint output_width, output_height;
  gsize pixel_stride;

  if (!filter->video_info_valid) {
    return FALSE;
  }

  /* Free old buffer if exists */
  if (filter->line_buffer) {
    g_free (filter->line_buffer);
    filter->line_buffer = NULL;
  }

  output_width = GST_VIDEO_INFO_WIDTH (&filter->video_info_out);
  output_height = GST_VIDEO_INFO_HEIGHT (&filter->video_info_out);
  pixel_stride = GST_VIDEO_INFO_COMP_PSTRIDE (&filter->video_info_out, 0);

  /* Calculate line size based on direction */
  if (filter->direction == GST_LINESCAN_DIRECTION_HORIZONTAL) {
    /* Extracting horizontal row: line is output_width pixels wide */
    filter->line_size = output_width * pixel_stride;
  } else {
    /* Extracting vertical column: line is 1 pixel wide */
    filter->line_size = pixel_stride;
  }

  /* Allocate buffer for entire output image */
  filter->line_buffer = g_malloc0 (GST_VIDEO_INFO_SIZE (&filter->video_info_out));
  if (!filter->line_buffer) {
    GST_ERROR_OBJECT (filter, "Failed to allocate line buffer");
    return FALSE;
  }

  filter->buffer_position = 0;

  GST_DEBUG_OBJECT (filter, "Allocated line buffer: %zu bytes, line size: %zu",
      GST_VIDEO_INFO_SIZE (&filter->video_info_out), filter->line_size);

  return TRUE;
}

static GstFlowReturn
gst_linescan_transform (GstBaseTransform * trans, GstBuffer * inbuf,
    GstBuffer * outbuf)
{
  GstLinescan *filter = GST_LINESCAN (trans);
  GstMapInfo map_in, map_out;
  guint8 *src_line, *dest_line;
  gint in_width, in_height, in_stride;
  gint out_width, out_height, out_stride;
  gint pixel_stride;
  gint x, y;

  if (!filter->video_info_valid || !filter->line_buffer) {
    GST_ERROR_OBJECT (filter, "Not properly initialized");
    return GST_FLOW_ERROR;
  }

  if (!gst_buffer_map (inbuf, &map_in, GST_MAP_READ)) {
    GST_ERROR_OBJECT (filter, "Failed to map input buffer");
    return GST_FLOW_ERROR;
  }

  if (!gst_buffer_map (outbuf, &map_out, GST_MAP_WRITE)) {
    GST_ERROR_OBJECT (filter, "Failed to map output buffer");
    gst_buffer_unmap (inbuf, &map_in);
    return GST_FLOW_ERROR;
  }

  in_width = GST_VIDEO_INFO_WIDTH (&filter->video_info_in);
  in_height = GST_VIDEO_INFO_HEIGHT (&filter->video_info_in);
  in_stride = GST_VIDEO_INFO_PLANE_STRIDE (&filter->video_info_in, 0);
  
  out_width = GST_VIDEO_INFO_WIDTH (&filter->video_info_out);
  out_height = GST_VIDEO_INFO_HEIGHT (&filter->video_info_out);
  out_stride = GST_VIDEO_INFO_PLANE_STRIDE (&filter->video_info_out, 0);
  
  pixel_stride = GST_VIDEO_INFO_COMP_PSTRIDE (&filter->video_info_in, 0);

  if (filter->direction == GST_LINESCAN_DIRECTION_HORIZONTAL) {
    /* Extract horizontal row */
    if (filter->actual_line_index >= in_height) {
      GST_WARNING_OBJECT (filter, "Line index %d exceeds input height %d",
          filter->actual_line_index, in_height);
      gst_buffer_unmap (inbuf, &map_in);
      gst_buffer_unmap (outbuf, &map_out);
      return GST_FLOW_ERROR;
    }

    /* Get pointer to the row we want to extract */
    src_line = map_in.data + (filter->actual_line_index * in_stride);

    /* Copy the row to the current position in our buffer */
    dest_line = filter->line_buffer + (filter->buffer_position * out_stride);
    memcpy (dest_line, src_line, filter->line_size);

  } else {
    /* Extract vertical column */
    if (filter->actual_line_index >= in_width) {
      GST_WARNING_OBJECT (filter, "Line index %d exceeds input width %d",
          filter->actual_line_index, in_width);
      gst_buffer_unmap (inbuf, &map_in);
      gst_buffer_unmap (outbuf, &map_out);
      return GST_FLOW_ERROR;
    }

    /* Extract column pixel by pixel and place horizontally in output */
    for (y = 0; y < in_height && y < out_height; y++) {
      src_line = map_in.data + (y * in_stride) + (filter->actual_line_index * pixel_stride);
      dest_line = filter->line_buffer + (y * out_stride) + (filter->buffer_position * pixel_stride);
      memcpy (dest_line, src_line, pixel_stride);
    }
  }

  /* Increment buffer position */
  filter->buffer_position++;

  /* Check for rollover and emit signal */
  gboolean rollover_occurred = FALSE;
  if (filter->direction == GST_LINESCAN_DIRECTION_HORIZONTAL) {
    if (filter->buffer_position >= out_height) {
      filter->buffer_position = 0;
      rollover_occurred = TRUE;
    }
  } else {
    if (filter->buffer_position >= out_width) {
      filter->buffer_position = 0;
      rollover_occurred = TRUE;
    }
  }

  /* Copy accumulated buffer to output */
  memcpy (map_out.data, filter->line_buffer, map_out.size);

  gst_buffer_unmap (inbuf, &map_in);
  gst_buffer_unmap (outbuf, &map_out);

  /* Emit rollover signal if buffer wrapped around */
  if (rollover_occurred) {
    GST_DEBUG_OBJECT (filter, "Rollover occurred at frame %lu",
        (unsigned long) filter->frame_count);
    g_signal_emit (filter, gst_linescan_signals[SIGNAL_ROLLOVER], 0, outbuf);
  }

  filter->frame_count++;

  GST_LOG_OBJECT (filter, "Processed frame %lu, buffer position: %d",
      (unsigned long) filter->frame_count, filter->buffer_position);

  return GST_FLOW_OK;
}

static void
gst_linescan_reset (GstLinescan * filter)
{
  if (filter->line_buffer) {
    g_free (filter->line_buffer);
    filter->line_buffer = NULL;
  }
  
  filter->buffer_position = 0;
  filter->frame_count = 0;
  
  if (filter->video_info_valid) {
    gst_linescan_allocate_buffer (filter);
  }
}

static gboolean
plugin_init (GstPlugin * plugin)
{
  return gst_element_register (plugin, "linescan", GST_RANK_NONE,
      GST_TYPE_LINESCAN);
}

GST_PLUGIN_DEFINE (GST_VERSION_MAJOR,
    GST_VERSION_MINOR,
    linescan,
    "Line scan camera simulator that extracts rows/columns from frames",
    plugin_init, GST_PACKAGE_VERSION, GST_PACKAGE_LICENSE, GST_PACKAGE_NAME,
    GST_PACKAGE_ORIGIN)