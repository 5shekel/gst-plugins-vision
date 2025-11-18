/* Simple Rollover Example - Linescan Buffer Capture Demo (C)
 *
 * This is a minimal C example showing rollover signal detection.
 *
 * NOTE: This example demonstrates signal connection but doesn't save files.
 * For actual file saving, use the Python examples (rollover_example.py or
 * launch_with_signal.py) which use PIL/numpy to properly save images.
 *
 * In C, you would need to:
 * 1. Map the buffer (gst_buffer_map)
 * 2. Parse the caps to get width/height/format
 * 3. Use a library like libpng or libjpeg to encode and save
 *
 * Compile with:
 * gcc rollover_example.c -o rollover_example `pkg-config --cflags --libs gstreamer-1.0 gstreamer-video-1.0`
 *
 * Usage:
 * ./rollover_example
 *
 * Pipeline:
 *   videotestsrc -> linescan -> videoconvert -> autovideosink
 *                       ↓
 *              (rollover signal)
 *                       ↓
 *            C callback prints message
 */

#include <gst/gst.h>
#include <gst/video/video.h>
#include <stdio.h>

static gint frame_counter = 0;

/* Callback function when rollover signal is emitted */
static void
on_rollover (GstElement *linescan, GstBuffer *buffer, gpointer user_data)
{
  GstCaps *caps;
  GstStructure *structure;
  gint width, height;
  const gchar *format_str;
  
  frame_counter++;
  
  /* Get buffer information */
  GstPad *srcpad = gst_element_get_static_pad (linescan, "src");
  caps = gst_pad_get_current_caps (srcpad);
  structure = gst_caps_get_structure (caps, 0);
  
  gst_structure_get_int (structure, "width", &width);
  gst_structure_get_int (structure, "height", &height);
  format_str = gst_structure_get_string (structure, "format");
  
  g_print ("[ROLLOVER] Frame %d - %dx%d %s (size: %lu bytes)\n",
           frame_counter,
           width, height,
           format_str,
           (unsigned long) gst_buffer_get_size (buffer));
  
  /* NOTE: To actually save the buffer to a file, you would:
   * 1. Map the buffer: gst_buffer_map(buffer, &map_info, GST_MAP_READ)
   * 2. Encode using libpng/libjpeg based on the data in map_info.data
   * 3. Write to file with the frame_counter in the filename
   * 4. Unmap: gst_buffer_unmap(buffer, &map_info)
   *
   * For a complete example with file saving, see the Python version.
   */
  
  gst_caps_unref (caps);
  gst_object_unref (srcpad);
}

int
main (int argc, char *argv[])
{
  GstElement *pipeline, *source, *linescan;
  GstElement *videoconvert, *videosink;
  GstBus *bus;
  GstMessage *msg;
  
  /* Initialize GStreamer */
  gst_init (&argc, &argv);
  
  /* Create elements - simplified pipeline without file branch */
  pipeline = gst_pipeline_new ("rollover-pipeline");
  source = gst_element_factory_make ("videotestsrc", "source");
  linescan = gst_element_factory_make ("linescan", "linescan");
  videoconvert = gst_element_factory_make ("videoconvert", "convert");
  videosink = gst_element_factory_make ("autovideosink", "videosink");
  
  if (!pipeline || !source || !linescan || !videoconvert || !videosink) {
    g_printerr ("Not all elements could be created.\n");
    g_printerr ("Make sure linescan plugin is built and in GST_PLUGIN_PATH.\n");
    return -1;
  }
  
  /* Configure elements */
  g_object_set (source, "pattern", 18, NULL);  /* ball pattern */
  g_object_set (linescan,
                "direction", 0,  /* horizontal */
                "line-index", 100,
                "output-size", 400,
                NULL);
  
  /* Connect to rollover signal */
  g_signal_connect (linescan, "rollover", G_CALLBACK (on_rollover), NULL);
  
  /* Build the pipeline - simple chain */
  gst_bin_add_many (GST_BIN (pipeline), source, linescan,
                    videoconvert, videosink, NULL);
  
  if (!gst_element_link_many (source, linescan, videoconvert, videosink, NULL)) {
    g_printerr ("Elements could not be linked.\n");
    gst_object_unref (pipeline);
    return -1;
  }
  
  /* Start playing */
  g_print ("Pipeline running. Rollover events will be printed.\n");
  g_print ("Press Ctrl+C to stop.\n\n");
  gst_element_set_state (pipeline, GST_STATE_PLAYING);
  
  /* Wait until error or EOS */
  bus = gst_element_get_bus (pipeline);
  msg = gst_bus_timed_pop_filtered (bus, GST_CLOCK_TIME_NONE,
                                     GST_MESSAGE_ERROR | GST_MESSAGE_EOS);
  
  /* Handle any errors */
  if (msg != NULL) {
    if (GST_MESSAGE_TYPE (msg) == GST_MESSAGE_ERROR) {
      GError *err;
      gchar *debug_info;
      gst_message_parse_error (msg, &err, &debug_info);
      g_printerr ("\nError: %s\n", err->message);
      g_error_free (err);
      g_free (debug_info);
    }
    gst_message_unref (msg);
  }
  
  /* Free resources */
  gst_object_unref (bus);
  gst_element_set_state (pipeline, GST_STATE_NULL);
  gst_object_unref (pipeline);
  
  g_print ("\nDetected %d rollover events\n", frame_counter);
  
  return 0;
}