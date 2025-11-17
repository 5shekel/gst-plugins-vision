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

#ifndef __GST_LINESCAN_H__
#define __GST_LINESCAN_H__

#include <gst/base/gstbasetransform.h>
#include <gst/video/video.h>

G_BEGIN_DECLS

#define GST_TYPE_LINESCAN \
  (gst_linescan_get_type())
#define GST_LINESCAN(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST((obj),GST_TYPE_LINESCAN,GstLinescan))
#define GST_LINESCAN_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_CAST((klass),GST_TYPE_LINESCAN,GstLinescanClass))
#define GST_IS_LINESCAN(obj) \
  (G_TYPE_CHECK_INSTANCE_TYPE((obj),GST_TYPE_LINESCAN))
#define GST_IS_LINESCAN_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_TYPE((klass),GST_TYPE_LINESCAN))

typedef struct _GstLinescan GstLinescan;
typedef struct _GstLinescanClass GstLinescanClass;

typedef enum {
  GST_LINESCAN_DIRECTION_HORIZONTAL = 0,  /* Extract row from each frame, stack vertically (width=input, height=output_size) */
  GST_LINESCAN_DIRECTION_VERTICAL         /* Extract column from each frame, stack horizontally (width=output_size, height=input) */
} GstLinescanDirection;

/**
 * GstLinescan:
 * @element: the parent element.
 *
 * Line scan plugin that extracts a single row or column from each frame
 * and builds them into an output image over time.
 */
struct _GstLinescan
{
  GstBaseTransform element;

  /* Properties */
  GstLinescanDirection direction;  /* HORIZONTAL or VERTICAL */
  gint line_index;                 /* Which row/column to extract (-1 = middle) */
  gint output_size;                /* Number of lines to accumulate (width for vertical, height for horizontal) */

  /* Video info */
  GstVideoInfo video_info_in;
  GstVideoInfo video_info_out;
  gboolean video_info_valid;

  /* Internal state */
  guint8 *line_buffer;             /* Buffer to accumulate lines */
  gint buffer_position;            /* Current position in buffer (how many lines accumulated) */
  gsize line_size;                 /* Size of one line in bytes */
  gint actual_line_index;          /* Computed line index to extract */
  guint64 frame_count;             /* Number of frames processed */
  
  gboolean output_caps_set;        /* Whether output caps have been negotiated */
};

struct _GstLinescanClass
{
  GstBaseTransformClass parent_class;
};

GType gst_linescan_get_type(void);

G_END_DECLS

#endif /* __GST_LINESCAN_H__ */