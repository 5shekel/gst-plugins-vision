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

#ifndef __GST_ROLLING_SUM_H__
#define __GST_ROLLING_SUM_H__

#include <gst/base/gstbasetransform.h>
#include <gst/video/video.h>

G_BEGIN_DECLS

#define GST_TYPE_ROLLING_SUM \
  (gst_rolling_sum_get_type())
#define GST_ROLLING_SUM(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST((obj),GST_TYPE_ROLLING_SUM,GstRollingSum))
#define GST_ROLLING_SUM_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_CAST((klass),GST_TYPE_ROLLING_SUM,GstRollingSumClass))
#define GST_IS_ROLLING_SUM(obj) \
  (G_TYPE_CHECK_INSTANCE_TYPE((obj),GST_TYPE_ROLLING_SUM))
#define GST_IS_ROLLING_SUM_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_TYPE((klass),GST_TYPE_ROLLING_SUM))

typedef struct _GstRollingSum GstRollingSum;
typedef struct _GstRollingSumClass GstRollingSumClass;

/**
 * GstRollingSum:
 * @element: the parent element.
 *
 * The opaque GstRollingSum data structure.
 */
struct _GstRollingSum
{
  GstBaseTransform element;

  /* Properties */
  gint window_size;      /* Number of frames in rolling window */
  gint column_index;     /* Which column to analyze (0-based) */
  gint stride;           /* Row sampling stride */
  gdouble threshold;     /* Deviation threshold for dropping frames */

  /* State */
  gdouble *ring_buffer;  /* Circular buffer of column means */
  gint ring_index;       /* Current position in ring buffer */
  gint frame_count;      /* Total frames processed */
  gdouble rolling_mean;  /* Current rolling mean */
  gdouble rolling_sum;   /* Current rolling sum for efficient mean update */
  
  /* Video format info */
  GstVideoInfo video_info;
  gboolean info_set;
};

struct _GstRollingSumClass
{
  GstBaseTransformClass parent_class;
};

GType gst_rolling_sum_get_type(void);

G_END_DECLS

#endif /* __GST_ROLLING_SUM_H__ */