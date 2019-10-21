/* GStreamer
 * Copyright (C) 2011 FIXME <fixme@example.com>
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
 * Free Software Foundation, Inc., 51 Franklin Street, Suite 500,
 * Boston, MA 02110-1335, USA.
 */
/**
 * SECTION:element-gstpleorasrc
 *
 * The pleorasrc element is a source for Pleora eBUS
 *
 * <refsect2>
 * <title>Example launch line</title>
 * |[
 * gst-launch -v pleorasrc ! videoconvert ! autovideosink
 * ]|
 * Shows video from the default Pleora device
 * </refsect2>
 */

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include <gst/gst.h>
#include <gst/base/gstpushsrc.h>
#include <gst/video/video.h>

#include "gstpleorasrc.h"

#include <PvConfigurationReader.h>
#include <PvDeviceGEV.h>
#include <PvDeviceU3V.h>
#include <PvStreamGEV.h>
#include <PvStreamU3V.h>
#include <PvSystem.h>
#include <PvVersion.h>

GST_DEBUG_CATEGORY_STATIC (gst_pleorasrc_debug);
#define GST_CAT_DEFAULT gst_pleorasrc_debug

/* prototypes */
static void gst_pleorasrc_set_property (GObject * object,
    guint property_id, const GValue * value, GParamSpec * pspec);
static void gst_pleorasrc_get_property (GObject * object,
    guint property_id, GValue * value, GParamSpec * pspec);
static void gst_pleorasrc_dispose (GObject * object);
static void gst_pleorasrc_finalize (GObject * object);

static gboolean gst_pleorasrc_start (GstBaseSrc * src);
static gboolean gst_pleorasrc_stop (GstBaseSrc * src);
static GstCaps *gst_pleorasrc_get_caps (GstBaseSrc * src, GstCaps * filter);
static gboolean gst_pleorasrc_set_caps (GstBaseSrc * src, GstCaps * caps);
static gboolean gst_pleorasrc_unlock (GstBaseSrc * src);
static gboolean gst_pleorasrc_unlock_stop (GstBaseSrc * src);

static GstFlowReturn gst_pleorasrc_create (GstPushSrc * src, GstBuffer ** buf);

static PvBuffer *gst_pleorasrc_get_pvbuffer (GstPleoraSrc * src);

enum
{
  PROP_0,
  PROP_DEVICE,
  PROP_DEVICE_INDEX,
  PROP_NUM_CAPTURE_BUFFERS,
  PROP_TIMEOUT,
  PROP_DETECTION_TIMEOUT,
  PROP_MULTICAST_GROUP,
  PROP_PORT,
  PROP_RECEIVER_ONLY,
  PROP_PACKET_SIZE,
  PROP_CONFIG_FILE,
  PROP_CONFIG_FILE_CONNECT
};

#define DEFAULT_PROP_DEVICE ""
#define DEFAULT_PROP_DEVICE_INDEX 0
#define DEFAULT_PROP_NUM_CAPTURE_BUFFERS 3
#define DEFAULT_PROP_TIMEOUT 1000
#define DEFAULT_PROP_DETECTION_TIMEOUT 1000
#define DEFAULT_PROP_MULTICAST_GROUP "0.0.0.0"
#define DEFAULT_PROP_PORT 1042
#define DEFAULT_PROP_RECEIVER_ONLY FALSE
#define DEFAULT_PROP_PACKET_SIZE 0
#define DEFAULT_PROP_CONFIG_FILE ""
#define DEFAULT_PROP_CONFIG_FILE_CONNECT TRUE

#define VIDEO_CAPS_MAKE_BAYER8(format)                     \
    "video/x-bayer, "                                        \
    "format = (string) " format ", "                         \
    "width = " GST_VIDEO_SIZE_RANGE ", "                     \
    "height = " GST_VIDEO_SIZE_RANGE ", "                    \
    "framerate = " GST_VIDEO_FPS_RANGE

#define VIDEO_CAPS_MAKE_BAYER16(format)                    \
    "video/x-bayer, "                                        \
    "format = (string) " format ", "                         \
    "endianness = (int) 1234, "                              \
    "bpp = (int) {16, 14, 12, 10}, "                         \
    "width = " GST_VIDEO_SIZE_RANGE ", "                     \
    "height = " GST_VIDEO_SIZE_RANGE ", "                    \
    "framerate = " GST_VIDEO_FPS_RANGE

/* pad templates */
static GstStaticPadTemplate gst_pleorasrc_src_template =
    GST_STATIC_PAD_TEMPLATE ("src",
    GST_PAD_SRC,
    GST_PAD_ALWAYS,
    GST_STATIC_CAPS (VIDEO_CAPS_MAKE_BAYER16
        ("{ bggr16, grbg16, rggb16, gbrg16 }") ";"
        VIDEO_CAPS_MAKE_BAYER8 ("{ bggr, grbg, rggb, gbrg }") ";"
        GST_VIDEO_CAPS_MAKE ("{ GRAY16_LE, GRAY16_BE, GRAY8, UYVY, YUY2, RGB }")
    )
    );

/* class initialization */

G_DEFINE_TYPE (GstPleoraSrc, gst_pleorasrc, GST_TYPE_PUSH_SRC);

static void
gst_pleorasrc_class_init (GstPleoraSrcClass * klass)
{
  GObjectClass *gobject_class = G_OBJECT_CLASS (klass);
  GstElementClass *gstelement_class = GST_ELEMENT_CLASS (klass);
  GstBaseSrcClass *gstbasesrc_class = GST_BASE_SRC_CLASS (klass);
  GstPushSrcClass *gstpushsrc_class = GST_PUSH_SRC_CLASS (klass);

  gobject_class->set_property = gst_pleorasrc_set_property;
  gobject_class->get_property = gst_pleorasrc_get_property;
  gobject_class->dispose = gst_pleorasrc_dispose;
  gobject_class->finalize = gst_pleorasrc_finalize;

  gst_element_class_add_pad_template (gstelement_class,
      gst_static_pad_template_get (&gst_pleorasrc_src_template));

  gst_element_class_set_static_metadata (gstelement_class,
      "Pleora Video Source", "Source/Video",
      "Pleora eBUS video source", "Joshua M. Doe <oss@nvl.army.mil>");

  gstbasesrc_class->start = GST_DEBUG_FUNCPTR (gst_pleorasrc_start);
  gstbasesrc_class->stop = GST_DEBUG_FUNCPTR (gst_pleorasrc_stop);
  gstbasesrc_class->get_caps = GST_DEBUG_FUNCPTR (gst_pleorasrc_get_caps);
  gstbasesrc_class->set_caps = GST_DEBUG_FUNCPTR (gst_pleorasrc_set_caps);
  gstbasesrc_class->unlock = GST_DEBUG_FUNCPTR (gst_pleorasrc_unlock);
  gstbasesrc_class->unlock_stop = GST_DEBUG_FUNCPTR (gst_pleorasrc_unlock_stop);

  gstpushsrc_class->create = GST_DEBUG_FUNCPTR (gst_pleorasrc_create);

  /* Install GObject properties */
  g_object_class_install_property (gobject_class, PROP_DEVICE,
      g_param_spec_string ("device", "Device ID",
          "Device ID. For GEV use MAC, IP, or user id. For U3V, use GUID or user id.",
          DEFAULT_PROP_DEVICE,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS |
              GST_PARAM_MUTABLE_READY)));
  g_object_class_install_property (gobject_class, PROP_DEVICE_INDEX,
      g_param_spec_int ("device-index", "Device index",
          "Index of device, use -1 to enumerate all and select last", -1,
          G_MAXINT, DEFAULT_PROP_DEVICE_INDEX,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));
  g_object_class_install_property (gobject_class, PROP_NUM_CAPTURE_BUFFERS,
      g_param_spec_uint ("num-capture-buffers", "Number of capture buffers",
          "Number of capture buffers", 1, G_MAXUINT,
          DEFAULT_PROP_NUM_CAPTURE_BUFFERS,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));
  g_object_class_install_property (G_OBJECT_CLASS (klass), PROP_TIMEOUT,
      g_param_spec_int ("timeout", "Timeout (ms)",
          "Timeout in ms (0 to use default)", 0, G_MAXINT, DEFAULT_PROP_TIMEOUT,
          (GParamFlags) (G_PARAM_STATIC_STRINGS | G_PARAM_READWRITE)));
  g_object_class_install_property (G_OBJECT_CLASS (klass),
      PROP_DETECTION_TIMEOUT, g_param_spec_int ("detection-timeout",
          "Detection Timeout (ms)", "Timeout in ms to detect GigE cameras", 100,
          60000, DEFAULT_PROP_DETECTION_TIMEOUT,
          (GParamFlags) (G_PARAM_STATIC_STRINGS | G_PARAM_READWRITE)));
  g_object_class_install_property (gobject_class, PROP_MULTICAST_GROUP,
      g_param_spec_string ("multicast-group", "Multicast group IP address",
          "The address of the multicast group to join (default is unicast)",
          DEFAULT_PROP_MULTICAST_GROUP,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS |
              GST_PARAM_MUTABLE_READY)));
  g_object_class_install_property (G_OBJECT_CLASS (klass), PROP_PORT,
      g_param_spec_int ("port", "Multicast port",
          "The port of the multicast group.", 0, 65535, DEFAULT_PROP_PORT,
          (GParamFlags) (G_PARAM_STATIC_STRINGS | G_PARAM_READWRITE)));
  g_object_class_install_property (G_OBJECT_CLASS (klass), PROP_RECEIVER_ONLY,
      g_param_spec_boolean ("receiver-only", "Receiver only",
          "Only open video stream, don't open as controller",
          DEFAULT_PROP_RECEIVER_ONLY,
          (GParamFlags) (G_PARAM_STATIC_STRINGS | G_PARAM_READWRITE)));
  g_object_class_install_property (G_OBJECT_CLASS (klass), PROP_PACKET_SIZE,
      g_param_spec_int ("packet-size", "Packet size",
          "Packet size (0 to auto negotiate)", 0, 65535,
          DEFAULT_PROP_PACKET_SIZE,
          (GParamFlags) (G_PARAM_STATIC_STRINGS | G_PARAM_READWRITE)));
  g_object_class_install_property (gobject_class, PROP_CONFIG_FILE,
      g_param_spec_string ("config-file", "Config file",
          "Filepath of the configuration file (*.pvcfg)",
          DEFAULT_PROP_CONFIG_FILE,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS |
              GST_PARAM_MUTABLE_READY)));
  g_object_class_install_property (G_OBJECT_CLASS (klass),
      PROP_CONFIG_FILE_CONNECT, g_param_spec_boolean ("config-file-connect",
          "Connect using config file",
          "Connects to and configures camera from config-file, if false "
          "connects using properties and then restores configuration",
          DEFAULT_PROP_CONFIG_FILE_CONNECT,
          (GParamFlags) (G_PARAM_STATIC_STRINGS | G_PARAM_READWRITE)));
}

static void
gst_pleorasrc_reset (GstPleoraSrc * src)
{
  src->device = NULL;
  src->stream = NULL;
  src->pipeline = NULL;

  src->last_frame_count = 0;
  src->total_dropped_frames = 0;

  if (src->caps) {
    gst_caps_unref (src->caps);
    src->caps = NULL;
  }

  src->pv_pixel_type = PvPixelUndefined;
  src->width = 0;
  src->height = 0;
}

static void
gst_pleorasrc_init (GstPleoraSrc * src)
{
  /* set source as live (no preroll) */
  gst_base_src_set_live (GST_BASE_SRC (src), TRUE);

  /* override default of BYTES to operate in time mode */
  gst_base_src_set_format (GST_BASE_SRC (src), GST_FORMAT_TIME);

  /* initialize member variables */
  src->device_id = g_strdup (DEFAULT_PROP_DEVICE);
  src->device_index = DEFAULT_PROP_DEVICE_INDEX;
  src->num_capture_buffers = DEFAULT_PROP_NUM_CAPTURE_BUFFERS;
  src->timeout = DEFAULT_PROP_TIMEOUT;
  src->detection_timeout = DEFAULT_PROP_DETECTION_TIMEOUT;
  src->multicast_group = g_strdup (DEFAULT_PROP_MULTICAST_GROUP);
  src->port = DEFAULT_PROP_PORT;
  src->receiver_only = DEFAULT_PROP_RECEIVER_ONLY;
  src->config_file = g_strdup (DEFAULT_PROP_CONFIG_FILE);
  src->config_file_connect = DEFAULT_PROP_CONFIG_FILE_CONNECT;

  src->stop_requested = FALSE;
  src->caps = NULL;

  src->pvbuffer = NULL;

  gst_pleorasrc_reset (src);
}

void
gst_pleorasrc_set_property (GObject * object, guint property_id,
    const GValue * value, GParamSpec * pspec)
{
  GstPleoraSrc *src;

  src = GST_PLEORA_SRC (object);

  switch (property_id) {
    case PROP_DEVICE:
      g_free (src->device_id);
      src->device_id = g_strdup (g_value_get_string (value));
      break;
    case PROP_DEVICE_INDEX:
      src->device_index = g_value_get_int (value);
      break;
    case PROP_NUM_CAPTURE_BUFFERS:
      src->num_capture_buffers = g_value_get_uint (value);
      break;
    case PROP_TIMEOUT:
      src->timeout = g_value_get_int (value);
      break;
    case PROP_DETECTION_TIMEOUT:
      src->detection_timeout = g_value_get_int (value);
      break;
    case PROP_MULTICAST_GROUP:
      g_free (src->multicast_group);
      src->multicast_group = g_strdup (g_value_get_string (value));
      break;
    case PROP_PORT:
      src->port = g_value_get_int (value);
      break;
    case PROP_RECEIVER_ONLY:
      src->receiver_only = g_value_get_boolean (value);
      break;
    case PROP_PACKET_SIZE:
      src->packet_size = g_value_get_int (value);
      break;
    case PROP_CONFIG_FILE:
      g_free (src->config_file);
      src->config_file = g_strdup (g_value_get_string (value));
      break;
    case PROP_CONFIG_FILE_CONNECT:
      src->config_file_connect = g_value_get_boolean (value);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, property_id, pspec);
      break;
  }
}

void
gst_pleorasrc_get_property (GObject * object, guint property_id,
    GValue * value, GParamSpec * pspec)
{
  GstPleoraSrc *src;

  g_return_if_fail (GST_IS_PLEORA_SRC (object));
  src = GST_PLEORA_SRC (object);

  switch (property_id) {
    case PROP_DEVICE:
      g_value_set_string (value, src->device_id);
      break;
    case PROP_DEVICE_INDEX:
      g_value_set_int (value, src->device_index);
      break;
    case PROP_NUM_CAPTURE_BUFFERS:
      g_value_set_uint (value, src->num_capture_buffers);
      break;
    case PROP_TIMEOUT:
      g_value_set_int (value, src->timeout);
      break;
    case PROP_DETECTION_TIMEOUT:
      g_value_set_int (value, src->detection_timeout);
      break;
    case PROP_MULTICAST_GROUP:
      g_value_set_string (value, src->multicast_group);
      break;
    case PROP_PORT:
      g_value_set_int (value, src->port);
      break;
    case PROP_RECEIVER_ONLY:
      g_value_set_boolean (value, src->receiver_only);
      break;
    case PROP_PACKET_SIZE:
      g_value_set_int (value, src->packet_size);
      break;
    case PROP_CONFIG_FILE:
      g_value_set_string (value, src->config_file);
      break;
    case PROP_CONFIG_FILE_CONNECT:
      g_value_set_boolean (value, src->config_file_connect);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, property_id, pspec);
      break;
  }
}

void
gst_pleorasrc_dispose (GObject * object)
{
  GstPleoraSrc *src;

  g_return_if_fail (GST_IS_PLEORA_SRC (object));
  src = GST_PLEORA_SRC (object);

  /* clean up as possible.  may be called multiple times */

  G_OBJECT_CLASS (gst_pleorasrc_parent_class)->dispose (object);
}

void
gst_pleorasrc_finalize (GObject * object)
{
  GstPleoraSrc *src;

  g_return_if_fail (GST_IS_PLEORA_SRC (object));
  src = GST_PLEORA_SRC (object);

  /* clean up object here */
  if (src->device) {
    g_free (src->device);
    src->device = NULL;
  }

  if (src->caps) {
    gst_caps_unref (src->caps);
    src->caps = NULL;
  }

  G_OBJECT_CLASS (gst_pleorasrc_parent_class)->finalize (object);
}

static const gchar *
usb_speed_str (PvUSBSpeed speed)
{
  static const gchar *array[] = {
    "Unknown", "Low", "Full", "High", "Super"
  };
  if (speed >= sizeof (array) / sizeof (const gchar *) || speed < 0) {
    speed = PvUSBSpeedUnknown;
  }
  return array[speed];
}

static const void
gst_pleorasrc_print_device_info (GstPleoraSrc * src,
    const PvDeviceInfo * device_info)
{
  GST_DEBUG_OBJECT (src, "Found device '%s'",
      device_info->GetDisplayID ().GetAscii ());

  const PvDeviceInfoGEV *device_info_GEV =
      dynamic_cast < const PvDeviceInfoGEV * >(device_info);
  const PvDeviceInfoU3V *device_info_U3V =
      dynamic_cast < const PvDeviceInfoU3V * >(device_info);
  const PvDeviceInfoUSB *device_info_USB =
      dynamic_cast < const PvDeviceInfoUSB * >(device_info);
  const PvDeviceInfoPleoraProtocol *device_info_pleora =
      dynamic_cast < const PvDeviceInfoPleoraProtocol * >(device_info);

  const PvNetworkAdapter *iface_nic =
      dynamic_cast < const PvNetworkAdapter * >(device_info->GetInterface ());
  const PvUSBHostController *iface_usb =
      dynamic_cast <
      const PvUSBHostController * >(device_info->GetInterface ());

  if (iface_nic != NULL) {
#if VERSION_MAJOR == 4
#define PLEORA_GET_PARAM
#else
#define PLEORA_GET_PARAM 0
#endif
    GST_DEBUG_OBJECT (src,
        "Device found on network interface '%s', MAC: %s, IP: %s, Subnet: %s",
        iface_nic->GetDescription ().GetAscii (),
        iface_nic->GetMACAddress ().GetAscii (),
        iface_nic->GetIPAddress (PLEORA_GET_PARAM).GetAscii (),
        iface_nic->GetSubnetMask (PLEORA_GET_PARAM).GetAscii ());
  } else if (iface_usb != NULL) {
    GST_DEBUG_OBJECT (src,
        "Device found on USB interface, VEN_%04X&DEV_%04X&SUBSYS_%08X&REV_%02X, '%s', %s Speed",
        iface_usb->GetVendorID (), iface_usb->GetDeviceID (),
        iface_usb->GetSubsystemID (), iface_usb->GetRevision (),
        iface_usb->GetName ().GetAscii (),
        usb_speed_str (iface_usb->GetSpeed ()));
  }

  if (device_info_GEV != NULL) {
    GST_DEBUG_OBJECT (src, "GEV device: MAC: %s, IP: %s, S/N: %s",
        device_info_GEV->GetMACAddress ().GetAscii (),
        device_info_GEV->GetIPAddress ().GetAscii (),
        device_info_GEV->GetSerialNumber ().GetAscii ());
  } else if (device_info_U3V != NULL) {
    GST_DEBUG_OBJECT (src, "U3V device: GUID: %s, S/N: %s",
        device_info_U3V->GetDeviceGUID ().GetAscii (),
        device_info_U3V->GetSerialNumber ().GetAscii (),
        device_info_U3V->GetInterface ());
  } else if (device_info_USB != NULL) {
    GST_DEBUG_OBJECT (src, "Unidentified USB device");
  } else if (device_info_pleora != NULL) {
    GST_DEBUG_OBJECT (src, "Pleora device: MAC: %s, IP: %s, S/N: %s",
        device_info_pleora->GetMACAddress ().GetAscii (),
        device_info_pleora->GetIPAddress ().GetAscii (),
        device_info_pleora->GetSerialNumber ().GetAscii ());
  }
}

static const PvDeviceInfo *
gst_pleorasrc_get_device_info (GstPleoraSrc * src, PvSystem & lSystem)
{
  PvResult pvRes;
  const PvDeviceInfo *device_info = NULL;

  // time allowed to detect GEV cameras
  lSystem.SetDetectionTimeout (src->detection_timeout);

  if (g_strcmp0 (src->device_id, "") != 0) {
    GST_DEBUG_OBJECT (src, "Finding device based on ID: %s", src->device_id);

    pvRes = lSystem.FindDevice (src->device_id, &device_info);

    if (!pvRes.IsOK ()) {
      GST_ELEMENT_ERROR (src, RESOURCE, NOT_FOUND,
          ("Failed to find device ID '%s': %s", src->device_id,
              pvRes.GetDescription ().GetAscii ()), (NULL));
      return NULL;
    }
  } else if (src->device_index >= 0) {
    GST_DEBUG_OBJECT (src, "Finding device based on index: %d",
        src->device_index);

    /* Find will block for detection_timeout */
    pvRes = lSystem.Find ();

    if (!pvRes.IsOK ()) {
      GST_ELEMENT_ERROR (src, RESOURCE, NOT_FOUND,
          ("Error finding devices: %s", pvRes.GetDescription ().GetAscii ()),
          (NULL));
      return NULL;
    }

    if (lSystem.GetDeviceCount () < 1) {
      GST_ELEMENT_ERROR (src, RESOURCE, NOT_FOUND,
          ("No Pleora-compatible devices found"), (NULL));
      return NULL;
    }

    if (src->device_index >= lSystem.GetDeviceCount ()) {
      GST_ELEMENT_ERROR (src, RESOURCE, NOT_FOUND,
          ("Device index specified (%d) does not exist, out of range [0, %d)",
              src->device_index, lSystem.GetDeviceCount ()), (NULL));
      return NULL;
    }

    device_info = lSystem.GetDeviceInfo (src->device_index);

    if (device_info == NULL) {
      GST_ELEMENT_ERROR (src, RESOURCE, NOT_FOUND,
          ("Failed to find device index %d", src->device_index), (NULL));
      return NULL;
    }
  } else {
    guint32 device_count;

    GST_DEBUG_OBJECT (src, "Enumerating devices and choosing last one");

    pvRes = lSystem.Find ();

    if (!pvRes.IsOK ()) {
      GST_ELEMENT_ERROR (src, RESOURCE, NOT_FOUND,
          ("Error finding devices: %s", pvRes.GetDescription ().GetAscii ()),
          (NULL));
      return NULL;
    }

    device_count = lSystem.GetDeviceCount ();

    if (device_count < 1) {
      GST_ELEMENT_ERROR (src, RESOURCE, NOT_FOUND,
          ("No Pleora-compatible devices found"), (NULL));
      return NULL;
    }

    GST_DEBUG_OBJECT (src, "Found a total of %d device(s)", device_count);
    for (uint32_t x = 0; x < device_count; x++) {
      device_info = lSystem.GetDeviceInfo (x);
      gst_pleorasrc_print_device_info (src, device_info);
    }

#if 0
    // iterate through all interfaces on system
    uint32_t lInterfaceCount = lSystem.GetInterfaceCount ();
    for (uint32_t x = 0; x < lInterfaceCount; x++) {
      const PvInterface *lInterface = lSystem.GetInterface (x);

      GST_DEBUG_OBJECT (src, "Found interface %d: '%s', '%s'", x,
          lInterface->GetName ().GetAscii (),
          lInterface->GetDisplayID ().GetAscii ());

      const PvNetworkAdapter *lNIC =
          dynamic_cast < const PvNetworkAdapter * >(lInterface);
      if (lNIC != NULL) {
        GST_DEBUG_OBJECT (src, "MAC: %s, IP: %s, Subnet: %s",
            lNIC->GetMACAddress ().GetAscii (),
            lNIC->GetIPAddress ().GetAscii (),
            lNIC->GetSubnetMask ().GetAscii ());
      }

      const PvUSBHostController *lUSB =
          dynamic_cast < const PvUSBHostController * >(lInterface);
      if (lUSB != NULL) {
        GST_DEBUG_OBJECT (src, "USB '%s'", lUSB->GetName ().GetAscii ());
      }
      // iterate through all devices on interface
      uint32_t lDeviceCount = lInterface->GetDeviceCount ();

      if (lDeviceCount == 0) {
        GST_DEBUG_OBJECT (src, "No devices found on this interface");
      }
      for (uint32_t y = 0; y < lDeviceCount; y++) {
        const PvDeviceInfo *devinfo = lInterface->GetDeviceInfo (y);

        gst_pleorasrc_print_device_info (src, devinfo);

        // select last device
        device_info = devinfo;
      }
    }
#endif

  }

  return device_info;
}

static gboolean
gst_pleorasrc_restore_device_from_config (GstPleoraSrc * src)
{
  PvConfigurationReader lConfigReader;
  PvResult pvRes;

  GST_DEBUG_OBJECT (src, "Loading config file (%s)", src->config_file);
  pvRes = lConfigReader.Load (src->config_file);
  if (!pvRes.IsOK ()) {
    GST_ELEMENT_ERROR (src, RESOURCE, SETTINGS,
        ("Failed to load config file (%s): %s",
            src->config_file, pvRes.GetDescription ().GetAscii ()), (NULL));
    return FALSE;
  }

  if (src->device == NULL) {
    PvDeviceGEV *lDeviceGEV = new PvDeviceGEV ();
    PvDeviceU3V *lDeviceU3V = new PvDeviceU3V ();

    GST_DEBUG_OBJECT (src,
        "Restoring device connection and settings from config file");
    pvRes = lConfigReader.Restore (0, lDeviceGEV);
    if (pvRes.IsOK ()) {
      src->device = lDeviceGEV;
      delete lDeviceU3V;
    } else {
      pvRes = lConfigReader.Restore (0, lDeviceU3V);
      if (pvRes.IsOK ()) {
        src->device = lDeviceU3V;
        delete lDeviceGEV;
      } else {
        GST_ELEMENT_ERROR (src, RESOURCE, SETTINGS,
            ("Failed to restore device from config file (%s): %s",
                src->config_file, pvRes.GetDescription ().GetAscii ()), (NULL));
        return FALSE;
      }
    }
  } else {
    GST_DEBUG_OBJECT (src, "Restoring device settings from config file");
    pvRes = lConfigReader.Restore (0, src->device);
    if (!pvRes.IsOK ()) {
      GST_ELEMENT_ERROR (src, RESOURCE, SETTINGS,
          ("Failed to restore device from config file (%s): %s",
              src->config_file, pvRes.GetDescription ().GetAscii ()), (NULL));
      return FALSE;
    }
  }

  return TRUE;
}

static gboolean
gst_pleorasrc_restore_stream_from_config (GstPleoraSrc * src)
{
  PvConfigurationReader lConfigReader;
  PvResult pvRes;

  GST_DEBUG_OBJECT (src, "Loading config file (%s)", src->config_file);
  pvRes = lConfigReader.Load (src->config_file);
  if (!pvRes.IsOK ()) {
    GST_ELEMENT_ERROR (src, RESOURCE, SETTINGS,
        ("Failed to load config file (%s): %s",
            src->config_file, pvRes.GetDescription ().GetAscii ()), (NULL));
    return FALSE;
  }

  if (src->stream == NULL) {
    PvStreamGEV *lStreamGEV = new PvStreamGEV ();
    PvStreamU3V *lStreamU3V = new PvStreamU3V ();

    GST_DEBUG_OBJECT (src,
        "Restoring stream connection and settings from config file");
    pvRes = lConfigReader.Restore (0, lStreamGEV);
    if (pvRes.IsOK ()) {
      src->stream = lStreamGEV;
      delete lStreamU3V;
    } else {
      pvRes = lConfigReader.Restore (0, lStreamU3V);
      if (pvRes.IsOK ()) {
        src->stream = lStreamU3V;
        delete lStreamGEV;
      } else {
        GST_ELEMENT_ERROR (src, RESOURCE, SETTINGS,
            ("Failed to restore stream from config file (%s): %s",
                src->config_file, pvRes.GetDescription ().GetAscii ()), (NULL));
        return FALSE;
      }
    }
  } else {
    GST_DEBUG_OBJECT (src, "Restoring stream settings from config file");
    pvRes = lConfigReader.Restore (0, src->stream);
    if (!pvRes.IsOK ()) {
      GST_ELEMENT_ERROR (src, RESOURCE, SETTINGS,
          ("Failed to restore stream from config file (%s): %s",
              src->config_file, pvRes.GetDescription ().GetAscii ()), (NULL));
      return FALSE;
    }
  }

  return TRUE;
}

static gboolean
gst_pleorasrc_setup_stream (GstPleoraSrc * src)
{
  PvResult pvRes;
  const PvDeviceInfo *device_info;
  PvSystem lSystem;

  if (g_strcmp0 (src->config_file, DEFAULT_PROP_CONFIG_FILE) != 0 &&
      src->config_file_connect) {
    if (!gst_pleorasrc_restore_device_from_config (src)) {
      /* error already sent */
      return FALSE;
    }

    if (!gst_pleorasrc_restore_stream_from_config (src)) {
      /* error already sent */
      return FALSE;
    }
  } else {
    /* PvSystem creates device info, so we must persist it across this call */
    device_info = gst_pleorasrc_get_device_info (src, lSystem);

    if (device_info == NULL) {
      /* error already sent */
      return FALSE;
    }

    GST_DEBUG_OBJECT (src, "Info for device that will be opened:");
    gst_pleorasrc_print_device_info (src, device_info);

    /* open device (for GEV, opening device means we're a controller */
    if (!src->receiver_only) {
      GST_DEBUG_OBJECT (src, "Trying to connect to device '%s' as controller",
          device_info->GetDisplayID ().GetAscii ());

      src->device = PvDevice::CreateAndConnect (device_info, &pvRes);
      if (src->device == NULL) {
        GST_ELEMENT_ERROR (src, RESOURCE, OPEN_READ,
            ("Unable to connect to device as controller: %s",
                pvRes.GetDescription ().GetAscii ()), (NULL));
        return FALSE;
      }
      GST_DEBUG_OBJECT (src, "Connected to device as controller");
    }

    /* open stream */
    if (device_info->GetType () == PvDeviceInfoTypeGEV ||
        device_info->GetType () == PvDeviceInfoTypePleoraProtocol) {
      PvStreamGEV *stream = new PvStreamGEV;
      if (g_strcmp0 (src->multicast_group, DEFAULT_PROP_MULTICAST_GROUP) != 0) {
        GST_DEBUG_OBJECT (src, "Opening device in multicast mode, %s:%d",
            src->multicast_group, src->port);
        pvRes =
            stream->Open (device_info->GetConnectionID (), src->multicast_group,
            src->port);
      } else {
        GST_DEBUG_OBJECT (src, "Opening device in unicast mode");
        pvRes = stream->Open (device_info->GetConnectionID ());
      }

      src->stream = stream;
    } else {
      src->stream =
          PvStream::CreateAndOpen (device_info->GetConnectionID (), &pvRes);
    }

    if (src->stream == NULL || !pvRes.IsOK ()) {
      GST_ELEMENT_ERROR (src, RESOURCE, OPEN_READ, ("Failed to open stream: %s",
              pvRes.GetDescription ().GetAscii ()), (NULL));
      goto stream_failed;
    }
    GST_DEBUG_OBJECT (src, "Stream created for device");

    /* if acting as a GigE controller, configure stream */
    PvDeviceGEV *lDeviceGEV = dynamic_cast < PvDeviceGEV * >(src->device);
    if (!src->receiver_only && lDeviceGEV != NULL) {
#if VERSION_MAJOR == 4
      PvStreamGEV *lStreamGEV = static_cast < PvStreamGEV * >(src->stream);
#else
      const PvStreamGEV *lStreamGEV =
          static_cast < PvStreamGEV * >(src->stream);
#endif

      /* negotiate or set packet size */
      if (src->packet_size == 0) {
        /* Negotiate packet size, use safe default if it fails */
        pvRes = lDeviceGEV->NegotiatePacketSize (0, 1476);
        if (!pvRes.IsOK ()) {
          GST_ELEMENT_ERROR (src, RESOURCE, SETTINGS,
              ("Failed to negotiate packet size: %s",
                  pvRes.GetDescription ().GetAscii ()), (NULL));
          goto stream_config_failed;
        }
      } else {
        pvRes = lDeviceGEV->SetPacketSize (src->packet_size);
        if (!pvRes.IsOK ()) {
          GST_ELEMENT_ERROR (src, RESOURCE, SETTINGS,
              ("Failed to set packet size to %d: %s", src->packet_size,
                  pvRes.GetDescription ().GetAscii ()), (NULL));
          goto stream_config_failed;
        }
      }

      /* Configure device streaming destination */
      pvRes =
          lDeviceGEV->SetStreamDestination (lStreamGEV->GetLocalIPAddress (),
          lStreamGEV->GetLocalPort ());

      if (!pvRes.IsOK ()) {
        GST_ELEMENT_ERROR (src, RESOURCE, SETTINGS,
            ("Failed to set stream destination: %s",
                pvRes.GetDescription ().GetAscii ()), (NULL));
        goto stream_config_failed;
      }
    }
  }

  /* load config file if specified */
  if (g_strcmp0 (src->config_file, DEFAULT_PROP_CONFIG_FILE) != 0 &&
      !src->config_file_connect) {
    if (!gst_pleorasrc_restore_device_from_config (src)) {
      goto stream_config_failed;
    }

    if (!gst_pleorasrc_restore_stream_from_config (src)) {
      goto stream_config_failed;
    }
  }

  src->pipeline = new PvPipeline (src->stream);
  if (src->pipeline == NULL) {
    GST_ELEMENT_ERROR (src, RESOURCE, OPEN_READ,
        ("Unable to create pipeline from stream"), (NULL));
    goto stream_config_failed;
  }

  pvRes = src->pipeline->SetBufferCount (src->num_capture_buffers);
  if (!pvRes.IsOK ()) {
    GST_ELEMENT_ERROR (src, RESOURCE, SETTINGS,
        ("Unable to set buffer count: %s", pvRes.GetDescription ().GetAscii ()),
        (NULL));
    goto pipeline_config_failed;
  }

  return TRUE;

pipeline_config_failed:
  if (src->pipeline) {
    delete src->pipeline;
    src->pipeline = NULL;
  }

stream_config_failed:
  if (src->stream) {
    src->stream->Close ();
    PvStream::Free (src->stream);
    src->stream = NULL;
  }

stream_failed:
  if (src->device) {
    src->device->Disconnect ();
    PvDevice::Free (src->device);
    src->device = NULL;
  }
  return FALSE;
}

// borrowed from Aravis, arvmisc.c
#define MAKE_FOURCC(a,b,c,d)        ((guint32)((a)|(b)<<8|(c)<<16|(d)<<24))

typedef struct
{
  PvPixelType pixel_type;
  const char *gst_caps_string;
  const char *name;
  const char *format;
  int bpp;
  int depth;
  guint32 fourcc;
} GstPleoraCapsInfos;

GstPleoraCapsInfos gst_caps_infos[] = {
  {
        PvPixelMono8,
        "video/x-raw, format=(string)GRAY8",
        "video/x-raw", "GRAY8",
      8, 8, 0},
  {
        PvPixelMono10,
        "video/x-raw, format=(string)GRAY16_LE, bpp=(int)10",
        "video/x-raw", "GRAY16_LE",
      10, 16, 0},
  {
        PvPixelMono12,
        "video/x-raw, format=(string)GRAY16_LE, bpp=(int)12",
        "video/x-raw", "GRAY16_LE",
      12, 16, 0},
  {
        PvPixelMono14,
        "video/x-raw, format=(string)GRAY16_LE, bpp=(int)14",
        "video/x-raw", "GRAY16_LE",
      14, 16, 0},
  {
        PvPixelMono16,
        "video/x-raw, format=(string)GRAY16_LE",
        "video/x-raw", "GRAY16_LE",
      16, 16, 0},
  {
        PvPixelBayerGR8,
        "video/x-bayer, format=(string)grbg",
        "video/x-bayer", "grbg",
        8, 8, MAKE_FOURCC ('g', 'r', 'b', 'g')
      },
  {
        PvPixelBayerRG8,
        "video/x-bayer, format=(string)rggb",
        "video/x-bayer", "rggb",
        8, 8, MAKE_FOURCC ('r', 'g', 'g', 'b')
      },
  {
        PvPixelBayerGB8,
        "video/x-bayer, format=(string)gbrg",
        "video/x-bayer", "gbrg",
        8, 8, MAKE_FOURCC ('g', 'b', 'r', 'g')
      },
  {
        PvPixelBayerBG8,
        "video/x-bayer, format=(string)bggr",
        "video/x-bayer", "bggr",
        8, 8, MAKE_FOURCC ('b', 'g', 'g', 'r')
      },

  /* The caps for non 8-bit bayer formats has not been agreed upon yet.
   * This feature is discussed in bug https://bugzilla.gnome.org/show_bug.cgi?id=693666 .*/
  {
        PvPixelBayerGR10,
        "video/x-bayer, format=(string)grbg16, bpp=(int)10",
        "video/x-bayer", "grbg",
      10, 16, 0},
  {
        PvPixelBayerRG10,
        "video/x-bayer, format=(string)rggb16, bpp=(int)10",
        "video/x-bayer", "rggb",
      10, 16, 0},
  {
        PvPixelBayerGB10,
        "video/x-bayer, format=(string)gbrg16, bpp=(int)10",
        "video/x-bayer", "gbrg",
      10, 16, 0},
  {
        PvPixelBayerBG10,
        "video/x-bayer, format=(string)bggr16, bpp=(int)10",
        "video/x-bayer", "bggr",
      10, 16, 0},
  {
        PvPixelBayerGR12,
        "video/x-bayer, format=(string)grbg16, bpp=(int)12",
        "video/x-bayer", "grbg",
      12, 16, 0},
  {
        PvPixelBayerRG12,
        "video/x-bayer, format=(string)rggb16, bpp=(int)12",
        "video/x-bayer", "rggb",
      12, 16, 0},
  {
        PvPixelBayerGB12,
        "video/x-bayer, format=(string)gbrg16, bpp=(int)12",
        "video/x-bayer", "gbrg",
      12, 16, 0},
  {
        PvPixelBayerBG12,
        "video/x-bayer, format=(string)bggr16, bpp=(int)12",
        "video/x-bayer", "bggr",
      12, 16, 0},
  {
        PvPixelBayerGR16,
        "video/x-bayer, format=(string)grbg16, bpp=(int)16",
        "video/x-bayer", "grbg",
      16, 16, 0},
  {
        PvPixelBayerRG16,
        "video/x-bayer, format=(string)rggb16, bpp=(int)16",
        "video/x-bayer", "rggb",
      16, 16, 0},
  {
        PvPixelBayerGB16,
        "video/x-bayer, format=(string)gbrg16, bpp=(int)16",
        "video/x-bayer", "gbrg",
      16, 16, 0},
  {
        PvPixelBayerBG16,
        "video/x-bayer, format=(string)bggr16, bpp=(int)16",
        "video/x-bayer", "bggr",
      16, 16, 0},

  {
        PvPixelYUV422_8_UYVY,
        "video/x-raw, format=(string)UYVY",
        "video/x-raw", "UYVY",
        0, 0, MAKE_FOURCC ('U', 'Y', 'V', 'Y')
      },
  {
        PvPixelYUV411_8_UYYVYY,
        "video/x-raw, format=(string)IYU1",
        "video/x-raw", "IYU1",
        0, 0, MAKE_FOURCC ('I', 'Y', 'U', '1')
      },
  {
        PvPixelYUV8_UYV,
        "video/x-raw, format=(string)IYU2",
        "video/x-raw", "IYU2",
        0, 0, MAKE_FOURCC ('I', 'Y', 'U', '2')
      },
  {
        PvPixelYUV422_8,
        "video/x-raw, format=(string)YUY2",
        "video/x-raw", "YUY2",
        0, 0, MAKE_FOURCC ('Y', 'U', 'Y', '2')
      },
  {
        PvPixelRGB8,
        "video/x-raw, format=(string)RGB",
        "video/x-raw", "RGB",
      24, 24, 0},
  {
        PvPixelRGBa8,
        "video/x-raw, format=(string)RGBx",
        "video/x-raw", "RGBx",
      32, 32, 0},
};

/**
 * arv_pixel_format_to_gst_caps_string:
 * @pixel_format: a pixel format
 * Return value: a gstreamer caps string describing the given @pixel_format.
 */

const char *
gst_pleorasrc_pixel_type_to_gst_caps_string (PvPixelType pixel_type)
{
  int i;

  for (i = 0; i < G_N_ELEMENTS (gst_caps_infos); i++)
    if (gst_caps_infos[i].pixel_type == pixel_type)
      break;

  if (i == G_N_ELEMENTS (gst_caps_infos)) {
    GST_WARNING ("Pixel type not currently supported: %d", pixel_type);
    return NULL;
  }

  GST_LOG ("Matched pixel type %d to caps %s",
      pixel_type, gst_caps_infos[i].gst_caps_string);

  return gst_caps_infos[i].gst_caps_string;
}

PvPixelType
gst_pleorasrc_pixel_type_from_gst_caps (const char *name,
    const char *format, int bpp, int depth)
{
  unsigned int i;

  g_return_val_if_fail (name != NULL, PvPixelUndefined);

  for (i = 0; i < G_N_ELEMENTS (gst_caps_infos); i++) {
    if (strcmp (name, gst_caps_infos[i].name) != 0 ||
        (depth > 0 && depth != gst_caps_infos[i].depth) ||
        (bpp > 0 && bpp != gst_caps_infos[i].bpp))
      continue;

    if (strcmp (name, "video/x-raw") == 0 &&
        strcmp (format, gst_caps_infos[i].format) == 0)
      return gst_caps_infos[i].pixel_type;

    if (strcmp (name, "video/x-bayer") == 0 &&
        strcmp (format, gst_caps_infos[i].format) == 0)
      return gst_caps_infos[i].pixel_type;
  }

  return PvPixelUndefined;
}

static gboolean
gst_pleorasrc_start (GstBaseSrc * bsrc)
{
  GstPleoraSrc *src = GST_PLEORA_SRC (bsrc);
  PvResult pvRes;

  GST_DEBUG_OBJECT (src, "start");

  if (!gst_pleorasrc_setup_stream (src)) {
    /* error already sent */
    goto error;
  }

  /* Note: the pipeline must be initialized before we start acquisition */
  GST_DEBUG_OBJECT (src, "Starting pipeline");
  pvRes = src->pipeline->Start ();
  if (!pvRes.IsOK ()) {
    GST_ELEMENT_ERROR (src, RESOURCE, FAILED, ("Failed to start pipeline: %s",
            pvRes.GetDescription ().GetAscii ()), (NULL));
    goto error;
  }

  /* command stream to start */
  if (!src->receiver_only) {
    PvGenParameterArray *lDeviceParams = src->device->GetParameters ();
    PvGenCommand *start_cmd =
        dynamic_cast <
        PvGenCommand * >(lDeviceParams->Get ("AcquisitionStart"));

    GST_DEBUG_OBJECT (src,
        "Opened as controller, so send AcquisitionStart command");

    if (start_cmd == NULL) {
      GST_ELEMENT_ERROR (src, RESOURCE, FAILED,
          ("Failed to get device AcquisitionStart parameter"), (NULL));
      goto error;
    }
    pvRes = src->device->StreamEnable ();
    if (!pvRes.IsOK ()) {
      GST_ELEMENT_ERROR (src, RESOURCE, FAILED, ("Failed to enable stream: %s",
              pvRes.GetDescription ().GetAscii ()), (NULL));
      goto error;
    }

    pvRes = start_cmd->Execute ();
    if (!pvRes.IsOK ()) {
      GST_ELEMENT_ERROR (src, RESOURCE, FAILED,
          ("Failed to start acquisition: %s",
              pvRes.GetDescription ().GetAscii ()), (NULL));
      goto error;
    }
  }

  /* grab first buffer so we can set caps before _create */
  src->pvbuffer = gst_pleorasrc_get_pvbuffer (src);
  if (!src->pvbuffer) {
    goto error;
  }

  return TRUE;

error:
  if (src->pipeline) {
    delete src->pipeline;
    src->pipeline = NULL;
  }

  if (src->stream) {
    src->stream->Close ();
    PvStream::Free (src->stream);
    src->stream = NULL;
  }

  if (src->device) {
    src->device->Disconnect ();
    PvDevice::Free (src->device);
    src->device = NULL;
  }

  return FALSE;
}

static gboolean
gst_pleorasrc_stop (GstBaseSrc * bsrc)
{
  GstPleoraSrc *src = GST_PLEORA_SRC (bsrc);
  GST_DEBUG_OBJECT (src, "stop");

  if (!src->receiver_only) {
    PvGenParameterArray *lDeviceParams = src->device->GetParameters ();
    PvGenCommand *lStop =
        dynamic_cast < PvGenCommand * >(lDeviceParams->Get ("AcquisitionStop"));
    lStop->Execute ();
    src->device->StreamDisable ();
  }
  src->pipeline->Stop ();

  if (src->pipeline) {
    delete src->pipeline;
    src->pipeline = NULL;
  }

  if (src->stream) {
    src->stream->Close ();
    PvStream::Free (src->stream);
    src->stream = NULL;
  }

  if (src->device) {
    src->device->Disconnect ();
    PvDevice::Free (src->device);
    src->device = NULL;
  }

  gst_pleorasrc_reset (src);

  return TRUE;
}

static GstCaps *
gst_pleorasrc_get_caps (GstBaseSrc * bsrc, GstCaps * filter)
{
  GstPleoraSrc *src = GST_PLEORA_SRC (bsrc);
  GstCaps *caps;

  if (src->caps == NULL) {
    caps = gst_pad_get_pad_template_caps (GST_BASE_SRC_PAD (src));
  } else {
    caps = gst_caps_copy (src->caps);
  }

  GST_DEBUG_OBJECT (src, "The caps before filtering are %" GST_PTR_FORMAT,
      caps);

  if (filter && caps) {
    GstCaps *tmp = gst_caps_intersect (caps, filter);
    gst_caps_unref (caps);
    caps = tmp;
  }

  GST_DEBUG_OBJECT (src, "The caps after filtering are %" GST_PTR_FORMAT, caps);

  return caps;
}

static gboolean
gst_pleorasrc_set_caps (GstBaseSrc * bsrc, GstCaps * caps)
{
  GstPleoraSrc *src = GST_PLEORA_SRC (bsrc);
  GstVideoInfo vinfo;
  GstStructure *s = gst_caps_get_structure (caps, 0);

  GST_DEBUG_OBJECT (src, "The caps being set are %" GST_PTR_FORMAT, caps);

  gst_video_info_from_caps (&vinfo, caps);

  if (GST_VIDEO_INFO_FORMAT (&vinfo) != GST_VIDEO_FORMAT_UNKNOWN) {
    src->height = GST_VIDEO_INFO_HEIGHT (&vinfo);
    src->gst_stride = GST_VIDEO_INFO_COMP_STRIDE (&vinfo, 0);
  } else {
    goto unsupported_caps;
  }

  return TRUE;

unsupported_caps:
  GST_ELEMENT_ERROR (src, RESOURCE, FAILED,
      ("Unsupported caps: %" GST_PTR_FORMAT, caps), (NULL));
  return FALSE;
}

static gboolean
gst_pleorasrc_unlock (GstBaseSrc * bsrc)
{
  GstPleoraSrc *src = GST_PLEORA_SRC (bsrc);

  GST_LOG_OBJECT (src, "unlock");

  src->stop_requested = TRUE;

  return TRUE;
}

static gboolean
gst_pleorasrc_unlock_stop (GstBaseSrc * bsrc)
{
  GstPleoraSrc *src = GST_PLEORA_SRC (bsrc);

  GST_LOG_OBJECT (src, "unlock_stop");

  src->stop_requested = FALSE;

  return TRUE;
}

//static GstBuffer *
//gst_pleorasrc_create_buffer_from_pvimage (GstPleoraSrc * src,
//    PvImage * pvimage)
//{
//  GstMapInfo minfo;
//  GstBuffer *buf;
//
//  /* TODO: use allocator or use from pool */
//  buf = gst_buffer_new_and_alloc (src->height * src->gst_stride);
//
//  /* Copy image to buffer from surface */
//  gst_buffer_map (buf, &minfo, GST_MAP_WRITE);
//  GST_LOG_OBJECT (src,
//      "GstBuffer size=%d, gst_stride=%d, buffer_num=%d, frame_count=%d, num_frames_on_queue=%d",
//      minfo.size, src->gst_stride, circ_handle->BufferNumber,
//      circ_handle->FrameCount, circ_handle->NumItemsOnQueue);
//  GST_LOG_OBJECT (src, "Buffer timestamp %02d:%02d:%02d.%06d",
//      circ_handle->HiResTimeStamp.hour, circ_handle->HiResTimeStamp.min,
//      circ_handle->HiResTimeStamp.sec, circ_handle->HiResTimeStamp.usec);
//
//  /* TODO: use orc_memcpy */
//  if (src->gst_stride == src->bf_stride) {
//    memcpy (minfo.data, ((guint8 *) circ_handle->pBufData), minfo.size);
//  } else {
//    int i;
//    GST_LOG_OBJECT (src, "Image strides not identical, copy will be slower.");
//    for (i = 0; i < src->height; i++) {
//      memcpy (minfo.data + i * src->gst_stride,
//          ((guint8 *) circ_handle->pBufData) +
//          i * src->bf_stride, src->bf_stride);
//    }
//  }
//  gst_buffer_unmap (buf, &minfo);
//
//  return buf;
//}

typedef struct
{
  GstPleoraSrc *src;
  PvBuffer *buffer;
} VideoFrame;

static void
pvbuffer_release (void *data)
{
  VideoFrame *frame = (VideoFrame *) data;
  if (frame->src->pipeline) {
    // TODO: should use a mutex in case _stop is being called at the same time
    frame->src->pipeline->ReleaseBuffer (frame->buffer);
  }
}

static PvBuffer *
gst_pleorasrc_get_pvbuffer (GstPleoraSrc * src)
{
  PvResult pvRes, opRes;
  PvBuffer *pvbuffer;
  PvImage *pvimage;

  while (TRUE) {
    pvRes = src->pipeline->RetrieveNextBuffer (&pvbuffer, src->timeout, &opRes);
    if (!pvRes.IsOK ()) {
      GST_ELEMENT_ERROR (src, RESOURCE, FAILED,
          ("Failed to retrieve buffer in timeout (%d ms): 0x%04x, '%s'",
              src->timeout, pvRes.GetCode (),
              pvRes.GetDescription ().GetAscii ()), (NULL));
      return NULL;
    }
    /* continue if we get a bad frame */
    if (!opRes.IsOK ()) {
      GST_WARNING_OBJECT (src, "Failed to get buffer: 0x%04x, '%s'",
          opRes.GetCode (), opRes.GetDescription ().GetAscii ());
      continue;
    }

    if (pvbuffer->GetPayloadType () != PvPayloadTypeImage) {
      /* TODO: are non-image buffers normal? */
      GST_ERROR_OBJECT (src, "Got buffer with non-image data");
      GST_ELEMENT_ERROR (src, RESOURCE, FAILED,
          ("Got buffer with non-image data"), (NULL));
      src->pipeline->ReleaseBuffer (pvbuffer);
      return NULL;
    }

    break;
  }

  pvimage = pvbuffer->GetImage ();

  if (src->pv_pixel_type != pvimage->GetPixelType () ||
      src->width != pvimage->GetWidth () ||
      src->height != pvimage->GetHeight ()) {
    const char *caps_string =
        gst_pleorasrc_pixel_type_to_gst_caps_string (pvimage->GetPixelType ());

    if (caps_string != NULL) {
      GstStructure *structure;
      GstCaps *caps;

      caps = gst_caps_new_empty ();
      structure = gst_structure_from_string (caps_string, NULL);
      gst_structure_set (structure,
          "width", G_TYPE_INT, pvimage->GetWidth (),
          "height", G_TYPE_INT, pvimage->GetHeight (),
          "framerate", GST_TYPE_FRACTION, 30, 1, NULL);
      gst_caps_append_structure (caps, structure);

      if (src->caps) {
        gst_caps_unref (src->caps);
      }
      src->caps = caps;
      gst_base_src_set_caps (GST_BASE_SRC (src), src->caps);

      src->pv_pixel_type = pvimage->GetPixelType ();
      src->width = pvimage->GetWidth ();
      src->height = pvimage->GetHeight ();

      guint32 pixel_bpp = PvGetPixelBitCount (pvimage->GetPixelType ());
      src->pleora_stride = (pvimage->GetWidth () * pixel_bpp) / 8;
    } else {
      GST_ELEMENT_ERROR (src, RESOURCE, FAILED, ("Pixel type %d not supported",
              pvimage->GetPixelType ()), (NULL));
      src->pipeline->ReleaseBuffer (pvbuffer);
      return NULL;
    }
  }

  return pvbuffer;
}

static GstFlowReturn
gst_pleorasrc_create (GstPushSrc * psrc, GstBuffer ** buf)
{
  GstPleoraSrc *src = GST_PLEORA_SRC (psrc);
  PvResult pvRes;
  GstClock *clock;
  GstClockTime clock_time;
  PvBuffer *pvbuffer;
  PvImage *pvimage;

  GST_LOG_OBJECT (src, "create");

  if (src->pvbuffer) {
    /* we have a buffer from _start to handle */
    pvbuffer = src->pvbuffer;
    src->pvbuffer = NULL;
  } else {
    pvbuffer = gst_pleorasrc_get_pvbuffer (src);
  }

  if (!pvbuffer) {
    /* error already posted */
    return GST_FLOW_ERROR;
  }

  pvimage = pvbuffer->GetImage ();

  gpointer data = pvimage->GetDataPointer ();
  if (src->pleora_stride == src->gst_stride) {
    VideoFrame *vf = g_new0 (VideoFrame, 1);
    vf->src = src;
    vf->buffer = pvbuffer;

    gsize data_size = pvimage->GetImageSize ();

    *buf =
        gst_buffer_new_wrapped_full ((GstMemoryFlags) GST_MEMORY_FLAG_READONLY,
        (gpointer) data, data_size, 0, data_size, vf,
        (GDestroyNotify) pvbuffer_release);
  } else {
    GstMapInfo minfo;

    GST_LOG_OBJECT (src,
        "Row stride not aligned, copying %d -> %d",
        src->pleora_stride, src->gst_stride);

    *buf = gst_buffer_new_and_alloc (src->height * src->gst_stride);

    guint8 *s = (guint8 *) data;
    guint8 *d;

    gst_buffer_map (*buf, &minfo, GST_MAP_WRITE);
    d = minfo.data;

    g_assert (minfo.size >= src->pleora_stride * src->height);
    for (int i = 0; i < src->height; i++)
      memcpy (d + i * src->gst_stride, s + i * src->pleora_stride,
          src->pleora_stride);
    gst_buffer_unmap (*buf, &minfo);

    src->pipeline->ReleaseBuffer (pvbuffer);
  }
  clock = gst_element_get_clock (GST_ELEMENT (src));
  clock_time = gst_clock_get_time (clock);
  gst_object_unref (clock);

  /* check for dropped frames and disrupted signal */
  //dropped_frames = (circ_handle.FrameCount - src->last_frame_count) - 1;
  //if (dropped_frames > 0) {
  //  src->total_dropped_frames += dropped_frames;
  //  GST_WARNING_OBJECT (src, "Dropped %d frames (%d total)", dropped_frames,
  //      src->total_dropped_frames);
  //} else if (dropped_frames < 0) {
  //  GST_WARNING_OBJECT (src, "Frame count non-monotonic, signal disrupted?");
  //}
  //src->last_frame_count = circ_handle.FrameCount;

  /* create GstBuffer then release circ buffer back to acquisition */
  //*buf = gst_pleorasrc_create_buffer_from_circ_handle (src, &circ_handle);
  //ret =
  //    BiCirStatusSet (src->board, &src->buffer_array, circ_handle, BIAVAILABLE);
  //if (ret != BI_OK) {
  //  GST_ELEMENT_ERROR (src, RESOURCE, FAILED,
  //      ("Failed to release buffer: %s", gst_pleorasrc_get_error_string (src,
  //              ret)), (NULL));
  //  return GST_FLOW_ERROR;
  //}

  /* TODO: understand why timestamps for circ_handle are sometimes 0 */
  //GST_BUFFER_TIMESTAMP (*buf) =
  //    GST_CLOCK_DIFF (gst_element_get_base_time (GST_ELEMENT (src)),
  //    src->acq_start_time + circ_handle.HiResTimeStamp.totalSec * GST_SECOND);
  GST_BUFFER_TIMESTAMP (*buf) =
      GST_CLOCK_DIFF (gst_element_get_base_time (GST_ELEMENT (src)),
      clock_time);
  //GST_BUFFER_OFFSET (*buf) = circ_handle.FrameCount - 1;

  if (src->stop_requested) {
    if (*buf != NULL) {
      gst_buffer_unref (*buf);
      *buf = NULL;
    }
    return GST_FLOW_FLUSHING;
  }

  return GST_FLOW_OK;
}


static gboolean
plugin_init (GstPlugin * plugin)
{
  GST_DEBUG_CATEGORY_INIT (gst_pleorasrc_debug, "pleorasrc", 0,
      "debug category for pleorasrc element");
  gst_element_register (plugin, "pleorasrc", GST_RANK_NONE,
      gst_pleorasrc_get_type ());

  return TRUE;
}

GST_PLUGIN_DEFINE (GST_VERSION_MAJOR,
    GST_VERSION_MINOR,
    pleora,
    "Pleora eBUS video source",
    plugin_init, GST_PACKAGE_VERSION, GST_PACKAGE_LICENSE, GST_PACKAGE_NAME,
    GST_PACKAGE_ORIGIN)
