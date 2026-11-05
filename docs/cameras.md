# Cameras

Add a camera on the Camera tab or the web page by typing its address. It can be:

- any camera on your network: a webcam a script shares from another computer, an IP camera, an
  ESP32-CAM. Its address and port (like `192.168.1.20:5656`) is enough: the picture is found on its
  page. A link straight to its stream or picture works too.
- a Pi with a USB camera: run `sudo bash setup.sh --camera` on it. If the camera turns (an OBSBOT,
  a PTZ webcam), the d-pad steers it.

Pis running the camera server show up by themselves under On your network. If a camera is on its
side, press Y on it in your list of cameras to rotate its picture. If it turns the wrong way when you
steer it, press START on it there for its settings: Flip left and right, and Flip up and down.
