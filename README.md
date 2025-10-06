#WI-FI BASED INDOOR NAVIGATION
Indoor navigation is becoming an essential feature in modern applications, from guiding
visitors inside airports and shopping malls to supporting emergency services in large
buildings. Unlike outdoor navigation, which can rely on GPS, positioning inside buildings
is more challenging due to the absence of satellite signals and the complexity of indoor
radio propagation.

In this repository, theres the code for a simple web application meant to function as a UI 
for WiFi based location.
By measuring the signal strength (RSSI) from multiple Wi-Fi access points placed at
known locations, it is possible to estimate the position of a mobile device within a
building. Different approaches can be applied, such as trilateration, where distances are
derived from signal strength, or fingerprinting, where signal patterns are compared to a
pre-collected database.
