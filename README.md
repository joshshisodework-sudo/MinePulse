# MineWatch

### Low-Cost Real-Time Mine Subsidence Monitoring and Early Warning System

**Smart India Hackathon 2026 — SIH26025**

---

## 1. Overview

MineWatch is a distributed monitoring system for detecting and tracking ground deformation associated with underground coal mining.

The system uses low-cost sensor nodes installed across the surface above and around underground mine panels. Each node measures physical parameters such as:

* Ground tilt
* Vibration
* Strain
* Relative movement

The measurements are locally processed and transmitted through a LoRa-based communication network to a gateway. The collected data is then stored, analysed and visualized through a central monitoring system.

The system is intended to support:

* Continuous ground monitoring
* Signal analysis
* Anomaly detection
* Spatial and temporal analysis
* Subsidence trend estimation
* GIS visualization
* Early warning

---

# 2. System Architecture

The complete system is organized into four main layers:

```text
┌──────────────────────────────────────┐
│          SENSOR LAYER                │
│ Tilt • Vibration • Strain • Movement │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│       COMMUNICATION LAYER            │
│              LoRa                    │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│        PROCESSING LAYER              │
│ Filtering • Features • Anomaly       │
│ Detection • Spatial Analysis         │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│       APPLICATION LAYER              │
│ GIS • Trends • Risk • Early Warning  │
└──────────────────────────────────────┘
```

---

# 3. Sensor Node

Each monitoring node is designed around a low-power microcontroller and sensors suitable for measuring ground behaviour.

| Component     | Function                                |
| ------------- | --------------------------------------- |
| STM32         | Sensor acquisition and local processing |
| BNO085        | Tilt / orientation measurement          |
| ADXL355       | High-resolution vibration measurement   |
| FBG sensors   | Strain and deformation measurement      |
| LoRa module   | Wireless communication                  |
| Battery       | Power source                            |
| Local storage | Temporary data buffering                |

The node periodically samples the sensors, performs basic processing and transmits the required measurements to the gateway.

---

# 4. Parameters Monitored

## Tilt

Measures changes in ground inclination. Persistent changes can indicate surface deformation.

## Vibration

Captures changes in the local vibration signature.

Relevant features include:

* RMS
* Peak amplitude
* Variance
* Kurtosis
* Crest factor
* Dominant frequency
* Frequency-band energy

## Strain

FBG-based sensing measures changes in local strain and deformation.

It can be used to identify:

* Ground stretching
* Local deformation
* Crack initiation
* Progressive movement

## Relative Movement

Measurements from neighbouring nodes can be compared to identify changes in the relative geometry of the monitored surface.

---

# 5. Local Signal Processing

Raw measurements are processed before transmission to reduce unnecessary data transfer while retaining relevant information.

Typical processing includes:

1. Filtering
2. Windowing
3. Statistical feature extraction
4. Frequency-domain analysis
5. Feature-vector generation

For vibration data, a time window can be converted into features such as RMS, peak amplitude, variance and dominant frequency.

---

# 6. LoRa Communication

The sensor nodes communicate with the gateway using LoRa.

The communication layer is designed for:

* Long-range transmission
* Low power consumption
* Distributed nodes
* Low data-rate sensor measurements
* Operation with limited network infrastructure

The proposed configuration uses the **IN865 band (865–867 MHz)**.

---

# 7. Gateway

The gateway provides the interface between the field sensor network and the monitoring software.

### Responsibilities

* Receive LoRa packets
* Validate node IDs
* Timestamp measurements
* Store incoming data
* Perform basic preprocessing
* Buffer data during connectivity loss
* Forward data to the central system

---

# 8. Node Deployment

Sensor placement is based on the geometry of the underground mining panel and the expected surface influence region.

A simplified estimate of the horizontal influence distance is:

$$
D = H\tan(\gamma)
$$

where:

* \(H\) = depth of the mining panel
* \(\gamma\) = angle of draw
* \(D\) = horizontal influence distance

For the initial deployment model:

$$
\gamma = 30^\circ
$$

For example, at a depth of \(250m\):

$$
D = 250\tan(30^\circ) \approx 144m
$$

The resulting influence region is then used to determine the monitoring area and sensor distribution.

---

# 9. Sensor Spacing

Different spacing can be used depending on the region being monitored.

### Edge Region

A higher sensor density can be used near the expected subsidence boundary:

$$
S = \frac{H}{8}
$$

### Internal Region

A comparatively larger spacing can be used farther from the boundary:

$$
S = \frac{H}{4}
$$

Actual spacing can be adjusted based on:

* Panel depth
* Panel geometry
* Expected deformation
* Terrain
* Sensor range
* Communication range

---

# 10. Reference Nodes

Stable reference nodes are positioned outside the expected affected region.

They provide a baseline against which measurements from potentially deforming areas can be compared.

This helps distinguish regional ground movement from changes caused by local environmental or sensor conditions.

---

# 11. Data Format

A typical monitoring packet can contain:

```text
Node ID
Timestamp
Battery Voltage
Tilt X
Tilt Y
Vibration RMS
Vibration Peak
Frequency Features
Strain
Communication Status
```

The packet structure can be extended as additional sensors are integrated.

---

# 12. Anomaly Detection

The initial deployment does not assume the availability of a large labelled mine-specific dataset.

An **Isolation Forest** is therefore used for initial anomaly detection.

The input consists of features describing the current state of a monitoring node, for example:

$$
X_i =
[
A_i,
RMS_i,
\sigma_i,
K_i,
T_i,
S_i
]
$$

where the terms represent selected vibration, tilt and strain features.

---

# 13. Isolation Forest

Isolation Forest constructs multiple random isolation trees.

For each observation:

1. A feature is selected.
2. A random split value is selected.
3. The observation is repeatedly partitioned.
4. The number of splits required to isolate it is recorded.
5. The process is repeated across multiple trees.
6. The path lengths are combined into an anomaly score.

Conceptually:

```text
Normal observation
       ↓
Longer isolation path
       ↓
Lower anomaly indication
```

```text
Unusual observation
       ↓
Shorter isolation path
       ↓
Higher anomaly indication
```

The anomaly score is used together with temporal and spatial information during risk assessment.

---

# 14. Initial Data Collection

The initial anomaly detector also provides a mechanism for identifying unusual observations while the system is collecting field data.

The collected measurements can subsequently be reviewed and classified to build a mine-specific dataset.

This gives the system a progressive development path:

```text
Initial deployment
       ↓
Field measurements
       ↓
Data validation
       ↓
Mine-specific dataset
       ↓
Improved prediction models
```

Isolation Forest is therefore an initial detection mechanism rather than the final prediction system.

---

# 15. Temporal Analysis

Subsidence is a progressive process, so measurements are analysed over time rather than as isolated values.

For each node, the system can maintain:

* Historical sensor measurements
* Anomaly scores
* Rate of change
* Moving averages
* Long-term trends

A persistent increase in deformation-related measurements is more significant than a single short-duration deviation.

---

# 16. Spatial Correlation

Neighbouring nodes are analysed together.

A single abnormal measurement can result from:

* Sensor error
* Temporary vibration
* Local disturbance
* Communication problems

Correlated changes across multiple neighbouring nodes provide stronger evidence of a spatially distributed event.

The monitoring system therefore considers both **node-level behaviour** and **neighbouring-node behaviour**.

---

# 17. Risk Assessment

Risk assessment combines multiple indicators rather than relying on a single sensor value.

Potential inputs include:

* Anomaly score
* Tilt change
* Strain change
* Vibration change
* Rate of deformation
* Historical trend
* Number of affected neighbouring nodes

The resulting state can be classified into operational levels such as:

| Level    | Meaning                                     |
| -------- | ------------------------------------------- |
| Normal   | No significant abnormal behaviour           |
| Watch    | Deviation requires observation              |
| Warning  | Persistent or correlated abnormal behaviour |
| Critical | Significant deformation indicators          |

The exact thresholds can be calibrated using field data.

---

# 18. GIS Dashboard

The monitoring interface provides a geographic representation of the monitored area.

### Main Elements

* Mine boundary
* Underground panel location
* Sensor locations
* Reference nodes
* Node status
* Historical measurements
* Anomaly locations
* Risk regions
* Subsidence trends

The GIS layer allows operators to relate sensor measurements to their physical location.

---

# 19. Early Warning

The warning system uses the results of sensor analysis, temporal trends, spatial correlation and risk assessment.

Warnings can be generated when measurements satisfy configured conditions such as:

* Persistent abnormal behaviour
* Rapid change in deformation
* Multiple neighbouring anomalous nodes
* Significant strain development
* Increasing vibration or tilt trends

The final warning is presented through the monitoring interface and can be connected to external notification mechanisms.

---

# 20. Fault Handling

Sensor faults must be separated from actual ground deformation.

The system therefore monitors:

* Battery voltage
* Packet loss
* Node availability
* Communication quality
* Sensor consistency
* Missing measurements
* Unrealistic values

A failed or inconsistent sensor can be classified as a sensor fault instead of immediately generating a subsidence warning.

---

# 21. Offline Data Handling

The gateway maintains local storage so that temporary loss of internet connectivity does not result in immediate data loss.

Measurements can be buffered locally and synchronized with the central system once connectivity is restored.

This is particularly important for field deployments where continuous internet connectivity cannot be guaranteed.

---

# 22. ML Development Path

The machine-learning component is developed progressively.

### Stage 1 — Initial Detection

Use Isolation Forest without requiring a large labelled dataset.

### Stage 2 — Field Data Collection

Collect real measurements from the deployed sensor network.

### Stage 3 — Data Validation

Review and classify observations using sensor behaviour, spatial relationships and available ground information.

### Stage 4 — Dataset Development

Build a mine-specific dataset from validated observations.

### Stage 5 — Prediction

Evaluate supervised models using the collected dataset.

Potential models include:

* XGBoost for structured sensor features
* LSTM for sequential measurements
* 1D CNN/LSTM architectures for vibration sequences

The final model should be selected based on the characteristics and volume of the collected dataset.

---

# 23. Technology Stack

### Embedded

* STM32
* BNO085
* ADXL355
* FBG sensors

### Communication

* LoRa
* IN865

### Signal Processing

* Digital filtering
* Windowing
* Statistical features
* Frequency-domain features

### Data Analysis

* Python
* NumPy
* Pandas
* Scikit-learn

### Machine Learning

* Isolation Forest
* XGBoost
* LSTM / temporal models where applicable

### Visualization

* GIS
* Web dashboard
* Time-series plots
* Risk maps

---

# 24. Development Stages

## Phase 1 — Sensor Node

* Integrate sensors
* Implement sampling
* Validate measurements
* Implement local processing

## Phase 2 — Communication

* Implement LoRa communication
* Develop packet format
* Test node-to-gateway communication
* Measure communication range

## Phase 3 — Gateway

* Receive and decode packets
* Implement local storage
* Implement data forwarding

## Phase 4 — Data Processing

* Filtering
* Feature extraction
* Time synchronization
* Data logging

## Phase 5 — Anomaly Detection

* Implement Isolation Forest
* Establish baseline behaviour
* Analyse field data

## Phase 6 — Spatial and Temporal Analysis

* Analyse neighbouring nodes
* Track deformation trends
* Generate risk information

## Phase 7 — Dashboard

* Integrate GIS
* Display sensor status
* Display trends
* Display anomalies and risk regions

## Phase 8 — Prediction and Early Warning

* Build validated dataset
* Evaluate prediction models
* Configure warning thresholds
* Validate the complete system

---

# 25. Summary

MineWatch combines distributed sensing, local signal processing, LoRa communication and centralized analysis into a continuous mine-surface monitoring system.

The system is designed to:

* Monitor ground conditions continuously
* Detect abnormal sensor behaviour
* Track temporal deformation trends
* Identify spatially correlated changes
* Visualize the monitored area through GIS
* Support progressive development of mine-specific prediction models
* Provide configurable early-warning information

The architecture is modular, allowing additional sensors, communication methods and analytical models to be incorporated as field data becomes available.
