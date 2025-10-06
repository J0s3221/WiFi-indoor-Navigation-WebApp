# Wi-Fi Based Indoor Navigation

Indoor navigation is becoming an essential feature in modern applications, from guiding visitors inside airports and shopping malls to supporting emergency services in large buildings. Unlike outdoor navigation, which can rely on GPS, positioning inside buildings is more challenging due to the absence of satellite signals and the complexity of indoor radio propagation.

## About This Project

This repository contains the code for a simple web application designed to function as a **UI for Wi-Fi-based indoor positioning**.

By measuring the signal strength (RSSI) from multiple Wi-Fi access points placed at known locations, it is possible to estimate the position of a mobile device within a building.  

Different approaches can be applied, such as:

- **Trilateration**: Distances are derived from signal strength to calculate the device's location.
- **Fingerprinting**: Signal patterns are compared to a pre-collected database to determine position.

