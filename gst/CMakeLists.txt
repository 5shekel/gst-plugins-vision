if (OPENCV_FOUND)
  add_subdirectory (sensorfx)
endif (OPENCV_FOUND)

add_subdirectory (bayerutils)
add_subdirectory (extractcolor)
add_subdirectory (intervalometer)

if (ENABLE_KLV)
  add_subdirectory (klv)
endif ()

add_subdirectory (misb)
add_subdirectory (rollingsum)
add_subdirectory (select)
add_subdirectory (videoadjust)
