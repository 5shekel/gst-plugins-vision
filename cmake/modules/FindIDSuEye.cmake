# - Try to find IDS uEye SDK
# Once done this will define
#
#  IDSUEYE_FOUND - system has IDS uEye SDK
#  IDSUEYE_INCLUDE_DIR - the IDS uEye SDK include directory
#  IDSUEYE_LIBRARIES - the libraries needed to use IDS uEye SDK

# Copyright (c) 2006, Tim Beaulen <tbscope@gmail.com>
# Copyright (c) 2017 outside US, United States Government, Joshua M. Doe <oss@nvl.army.mil>
#
# Redistribution and use is allowed according to the terms of the BSD license.
# For details see the accompanying COPYING-CMAKE-SCRIPTS file.
if (WIN32)
    if (NOT IDSUEYE_DIR)
    set (IDSUEYE_DIR "C:/Program Files/IDS/uEye/Develop" CACHE PATH "Directory containing IDS uEye SDK includes and libraries")
    endif ()

    if (CMAKE_SIZEOF_VOID_P MATCHES "8")
    set(_LIB_NAME "uEye_api_64")
    else ()
    set(_LIB_NAME "uEye_api")
    endif ()

    find_path (IDSUEYE_INCLUDE_DIR uEye.h
    PATHS
    "${IDSUEYE_DIR}/include"
    DOC "Directory containing IDS uEye include files")
endif (WIN32)

if (UNIX)
    if (NOT IDSUEYE_DIR)
        set (IDSUEYE_DIR "/opt/ids/ueye" CACHE PATH "Directory containing IDS uEye SDK includes and libraries")
    endif ()

    set(_LIB_NAME "libueye_api.so")

    find_path (IDSUEYE_INCLUDE_DIR uEye.h
    PATHS
    "${CMAKE_CURRENT_SOURCE_DIR}/sys/idsueye/include"
    "${IDSUEYE_DIR}/include"
    "/opt/ids/ueye/include"
    "/usr/include/ueye"
    "/usr/include"
    DOC "Directory containing IDS uEye include files")
endif (UNIX)

find_library (_uEyeLib NAMES ${_LIB_NAME}
PATHS
"${IDSUEYE_DIR}/lib"
"${IDSUEYE_DIR}/lib/aarch64-linux-gnu"
"${IDSUEYE_DIR}/lib/arm-linux-gnueabihf"
"/opt/ids/ueye/lib"
"/opt/ids/ueye/lib/aarch64-linux-gnu"
"/opt/ids/ueye/lib/arm-linux-gnueabihf"
"${IDSUEYE_DIR}/Lib")

set (IDSUEYE_LIBRARIES ${_uEyeLib})

mark_as_advanced (_uEyeLib)

include (FindPackageHandleStandardArgs)
find_package_handle_standard_args (IDSUEYE  DEFAULT_MSG  IDSUEYE_INCLUDE_DIR IDSUEYE_LIBRARIES)
