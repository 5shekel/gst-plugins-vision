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

#ifndef __GST_INTERVALOMETER_H__
#define __GST_INTERVALOMETER_H__

#include <stdio.h>
#include <gst/base/gstbasetransform.h>
#include <gst/video/video.h>

#define _PURE_C
#include "../../sys/idsueye/include/uEye.h"

G_BEGIN_DECLS

#define GST_TYPE_INTERVALOMETER \
  (gst_intervalometer_get_type())
#define GST_INTERVALOMETER(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST((obj),GST_TYPE_INTERVALOMETER,GstIntervalometer))
#define GST_INTERVALOMETER_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_CAST((klass),GST_TYPE_INTERVALOMETER,GstIntervalometerClass))
#define GST_IS_INTERVALOMETER(obj) \
  (G_TYPE_CHECK_INSTANCE_TYPE((obj),GST_TYPE_INTERVALOMETER))
#define GST_IS_INTERVALOMETER_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_TYPE((klass),GST_TYPE_INTERVALOMETER))

typedef struct _GstIntervalometer GstIntervalometer;
typedef struct _GstIntervalometerClass GstIntervalometerClass;

typedef enum {
  RAMP_RATE_VSLOW = 0,
  RAMP_RATE_SLOW,
  RAMP_RATE_MEDIUM,
  RAMP_RATE_FAST,
  RAMP_RATE_VFAST
} GstIntervalometerRampRate;

/**
 * GstIntervalometer:
 * @element: the parent element.
 *
 * Auto-exposure controller for IDS uEye cameras.
 * Inspired by YASS (Yet Another Sunset Script) for CHDK cameras.
 */
struct _GstIntervalometer
{
  GstBaseTransform element;

  /* Properties */
  gboolean enabled;
  gdouble target_brightness;     /* Target average brightness (0-255) */
  gdouble compensation;          /* Exposure compensation in stops */
  gdouble exposure_min;          /* Minimum exposure in ms */
  gdouble exposure_max;          /* Maximum exposure in ms */
  gint gain_min;                 /* Minimum gain (0-100) */
  gint gain_max;                 /* Maximum gain (0-100) */
  GstIntervalometerRampRate ramp_rate;
  gchar *log_file;               /* CSV log file path */
  gboolean log_append;           /* Open log_file in append mode (keep history across restarts) */
  gchar *camera_element_name;    /* Name of upstream idsueyesrc element */
  guint update_interval;         /* Update interval in milliseconds */
  gdouble brightness_smoothing;  /* Brightness smoothing factor (0-1, 0=no smoothing) */
  gdouble brightness_deadband;   /* Deadband zone to prevent oscillation (0=disabled) */
  gboolean auto_gain_boost;      /* Toggle camera gain-boost as a third rung below exposure+gain */
  gdouble boost_min_dwell;       /* Minimum seconds between gain-boost toggles (anti-chatter) */
  gint gain_max_boost;           /* Gain ceiling while gain-boost is active (0 = use gain_max) */

  /* Internal state */
  GstElement *camera_src;        /* Reference to upstream camera element */
  HIDS hCam;                     /* IDS uEye camera handle from idsueyesrc */
  gdouble current_exposure;      /* Current exposure setting */
  gint current_gain;             /* Current gain setting */
  gdouble target_exposure;       /* Target exposure for ramping */
  gint target_gain;              /* Target gain for ramping */
  gboolean boost_active;         /* Current camera gain-boost state (queried, then tracked) */

  guint64 frame_count;           /* Number of frames processed */
  GstClockTime start_time;       /* Time when processing started */
  GstClockTime last_update_time; /* Time of last algorithm update */
  GstClockTime last_boost_toggle_time; /* Time gain-boost was last toggled (dwell guard) */
  
  FILE *log_fp;                  /* Log file handle */
  gboolean log_header_written;   /* Whether CSV header has been written */
  
  /* Video info */
  GstVideoInfo video_info;
  gboolean video_info_valid;
  
  /* Brightness smoothing */
  gdouble smoothed_brightness;   /* Exponentially smoothed brightness value */
  gboolean brightness_initialized; /* Whether smoothed_brightness has been initialized */
  
  /* Ramping parameters */
  gdouble ramp_step;             /* Current ramping step size */
};

struct _GstIntervalometerClass
{
  GstBaseTransformClass parent_class;
};

GType gst_intervalometer_get_type(void);

G_END_DECLS

#endif /* __GST_INTERVALOMETER_H__ */