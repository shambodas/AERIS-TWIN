"""
AERIS-TWIN
Engine Vibration / Spectral Feature Model

Purpose
-------
Generate a physically-inspired vibration signal from engine
rotational speed and operating condition.

Pipeline:

    Engine RPM
        ↓
    Rotational frequency
        ↓
    Order components
        ↓
    Time-domain vibration signal
        ↓
    FFT
        ↓
    Spectral features

Primary features:

    - RMS vibration
    - Peak vibration
    - Crest factor
    - 0.5X amplitude
    - 1X amplitude
    - 2X amplitude
    - Dominant frequency
    - Spectral centroid

Fault-sensitive signatures:

    MISFIRE
        → increased firing irregularity
        → stronger sub-order components
        → increased vibration

    COMBUSTION_INSTABILITY
        → increased stochastic vibration

    COOLING_DEGRADATION
        → small secondary vibration effect

Model type
----------
Physics-inspired signal synthesis and spectral feature
extraction.

IMPORTANT
---------
This is not a replacement for measured accelerometer data.
The generated signal is intended for Digital Twin and ML
proof-of-concept development.

For final validation, measured vibration data should be used.
"""


from dataclasses import dataclass

import math
import random

import numpy as np


# ============================================================
# CONSTANTS
# ============================================================

DEFAULT_SAMPLE_RATE_HZ = 1000.0

DEFAULT_WINDOW_SECONDS = 1.0

# Number of samples in the default window
DEFAULT_NUM_SAMPLES = int(
    DEFAULT_SAMPLE_RATE_HZ
    * DEFAULT_WINDOW_SECONDS
)

# Reference vibration amplitude
BASE_VIBRATION_AMPLITUDE = 0.20

# Noise level
BASE_NOISE_STD = 0.025


# ============================================================
# DATA STRUCTURE
# ============================================================

@dataclass
class VibrationState:
    """
    Vibration output for one simulation window.
    """

    rpm: float

    rotational_frequency_hz: float

    sample_rate_hz: float

    signal_rms: float

    signal_peak: float

    crest_factor: float

    dominant_frequency_hz: float

    spectral_centroid_hz: float

    order_0_5x: float

    order_1x: float

    order_2x: float

    time_signal: np.ndarray


# ============================================================
# VIBRATION MODEL
# ============================================================

class EngineVibrationModel:
    """
    Physics-inspired vibration signal generator.

    The model uses rotational order components.

    For rotational frequency:

        f_rot = RPM / 60

    an order k corresponds to:

        f_k = k × f_rot

    The signal is constructed as a superposition of:

        0.5X
        1X
        2X
        firing-related components
        broadband noise
    """

    def __init__(
        self,
        sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
    ):

        if sample_rate_hz <= 0:

            raise ValueError(
                "Sample rate must be positive."
            )

        if window_seconds <= 0:

            raise ValueError(
                "Window duration must be positive."
            )

        self.sample_rate_hz = (
            sample_rate_hz
        )

        self.window_seconds = (
            window_seconds
        )

        self.num_samples = int(
            sample_rate_hz
            * window_seconds
        )


    # ========================================================
    # ROTATIONAL FREQUENCY
    # ========================================================

    @staticmethod
    def rpm_to_frequency(
        rpm: float
    ) -> float:
        """
        Convert RPM to rotational frequency.

            f = RPM / 60
        """

        return max(
            0.0,
            rpm
        ) / 60.0


    # ========================================================
    # ORDER FREQUENCY
    # ========================================================

    @staticmethod
    def order_frequency(
        rotational_frequency_hz: float,
        order: float,
    ) -> float:
        """
        Calculate frequency corresponding to an engine order.
        """

        return (
            rotational_frequency_hz
            * order
        )


    # ========================================================
    # FAULT AMPLITUDES
    # ========================================================

    def _calculate_component_amplitudes(
        self,
        wear_index: float,
        fault_state: dict | None,
    ):
        """
        Calculate order-component amplitudes.

        Returns
        -------
        tuple:
            amplitude_0_5x,
            amplitude_1x,
            amplitude_2x,
            instability_noise
        """

        wear_index = max(
            0.0,
            min(1.0, wear_index)
        )

        amp_0_5x = (
            0.04
            + 0.03 * wear_index
        )

        amp_1x = (
            BASE_VIBRATION_AMPLITUDE
            + 0.15 * wear_index
        )

        amp_2x = (
            0.06
            + 0.05 * wear_index
        )

        instability_noise = (
            BASE_NOISE_STD
        )

        if fault_state is None:

            return (
                amp_0_5x,
                amp_1x,
                amp_2x,
                instability_noise,
            )

        fault_type = fault_state.get(
            "type",
            "NONE"
        )

        severity = float(
            fault_state.get(
                "severity",
                0.0
            )
        )

        severity = max(
            0.0,
            min(1.0, severity)
        )

        # ----------------------------------------------------
        # MISFIRE
        # ----------------------------------------------------

        if fault_type == "MISFIRE":

            # Misfire creates a strong sub-order signature
            # because combustion becomes uneven between
            # cylinders.

            amp_0_5x += (
                1.8
                * severity ** 1.4
            )

            amp_1x += (
                0.8
                * severity
            )

            amp_2x += (
                0.25
                * severity
            )

        # ----------------------------------------------------
        # COMBUSTION INSTABILITY
        # ----------------------------------------------------

        elif fault_type == (
            "COMBUSTION_INSTABILITY"
        ):

            amp_1x += (
                0.25
                * severity
            )

            amp_2x += (
                0.8
                * severity
            )

            instability_noise += (
                0.10
                * severity
            )

        # ----------------------------------------------------
        # EXCESSIVE VIBRATION
        # ----------------------------------------------------

        elif fault_type == (
            "EXCESSIVE_VIBRATION"
        ):

            amp_1x += (
                1.5
                * severity
            )

            instability_noise += (
                0.05
                * severity
            )

        # ----------------------------------------------------
        # COOLING DEGRADATION
        # ----------------------------------------------------

        elif fault_type == (
            "COOLING_DEGRADATION"
        ):

            # Cooling degradation is primarily thermal, so
            # vibration impact is intentionally small.

            amp_1x += (
                0.10
                * severity
            )

        return (
            amp_0_5x,
            amp_1x,
            amp_2x,
            instability_noise,
        )


    # ========================================================
    # TIME DOMAIN SIGNAL
    # ========================================================

    def generate_signal(
        self,
        rpm: float,
        wear_index: float = 0.0,
        fault_state: dict | None = None,
    ) -> np.ndarray:
        """
        Generate a vibration time-domain signal.

        The signal contains:

            0.5X component
            1X component
            2X component
            firing-related harmonic
            broadband noise
        """

        rpm = max(
            0.0,
            rpm
        )

        rotational_frequency = (
            self.rpm_to_frequency(
                rpm
            )
        )

        # ----------------------------------------------------
        # Time vector
        # ----------------------------------------------------

        t = (
            np.arange(
                self.num_samples
            )
            / self.sample_rate_hz
        )

        # ----------------------------------------------------
        # Component amplitudes
        # ----------------------------------------------------

        (
            amp_0_5x,
            amp_1x,
            amp_2x,
            noise_std,
        ) = self._calculate_component_amplitudes(
            wear_index,
            fault_state,
        )

        # ----------------------------------------------------
        # Phase values
        # ----------------------------------------------------

        phase_0_5x = random.uniform(
            0.0,
            2.0 * math.pi
        )

        phase_1x = random.uniform(
            0.0,
            2.0 * math.pi
        )

        phase_2x = random.uniform(
            0.0,
            2.0 * math.pi
        )

        # ----------------------------------------------------
        # Order frequencies
        # ----------------------------------------------------

        f_0_5x = (
            0.5
            * rotational_frequency
        )

        f_1x = rotational_frequency

        f_2x = (
            2.0
            * rotational_frequency
        )

        # ----------------------------------------------------
        # Base signal
        # ----------------------------------------------------

        signal = (

            amp_0_5x
            * np.sin(
                2.0
                * math.pi
                * f_0_5x
                * t
                + phase_0_5x
            )

            +

            amp_1x
            * np.sin(
                2.0
                * math.pi
                * f_1x
                * t
                + phase_1x
            )

            +

            amp_2x
            * np.sin(
                2.0
                * math.pi
                * f_2x
                * t
                + phase_2x
            )
        )

        # ----------------------------------------------------
        # Firing-related harmonic
        # ----------------------------------------------------

        # For a four-cylinder four-stroke engine, there are
        # two firing events per crank revolution on average.
        #
        # This produces a representative 2X firing component.

        firing_frequency = (
            2.0
            * rotational_frequency
        )

        firing_amplitude = (
            0.08
            + 0.05 * wear_index
        )

        # Misfire produces firing irregularity.
        if (
            fault_state is not None
            and fault_state.get("type")
            == "MISFIRE"
        ):

            severity = float(
                fault_state.get(
                    "severity",
                    0.0
                )
            )

            firing_amplitude *= (
                1.0
                + 2.0 * severity
            )

        signal += (
            firing_amplitude
            * np.sin(
                2.0
                * math.pi
                * firing_frequency
                * t
            )
        )

        # ----------------------------------------------------
        # Broadband noise
        # ----------------------------------------------------

        noise = np.random.normal(
            0.0,
            noise_std,
            self.num_samples,
        )

        signal += noise

        # ----------------------------------------------------
        # Remove DC component
        # ----------------------------------------------------

        signal -= np.mean(
            signal
        )

        return signal


    # ========================================================
    # FFT
    # ========================================================

    def calculate_fft(
        self,
        signal: np.ndarray,
    ):
        """
        Calculate single-sided FFT magnitude spectrum.
        """

        if len(signal) == 0:

            raise ValueError(
                "Signal cannot be empty."
            )

        n = len(signal)

        window = np.hanning(n)

        windowed_signal = (
            signal
            * window
        )

        spectrum = np.fft.rfft(
            windowed_signal
        )

        frequencies = (
            np.fft.rfftfreq(
                n,
                d=1.0
                / self.sample_rate_hz,
            )
        )

        magnitude = (
            np.abs(spectrum)
            * 2.0
            / n
        )

        return (
            frequencies,
            magnitude,
        )


    # ========================================================
    # ORDER AMPLITUDE
    # ========================================================

    @staticmethod
    def extract_order_amplitude(
        frequencies: np.ndarray,
        magnitude: np.ndarray,
        rotational_frequency_hz: float,
        order: float,
        bandwidth_fraction: float = 0.05,
    ) -> float:
        """
        Extract amplitude around an engine order.

        Example:

            order = 1.0
                → 1X rotational component

            order = 0.5
                → 0.5X component
        """

        target_frequency = (
            rotational_frequency_hz
            * order
        )

        if target_frequency <= 0:

            return 0.0

        bandwidth = max(
            1.0,
            target_frequency
            * bandwidth_fraction
        )

        lower = (
            target_frequency
            - bandwidth
        )

        upper = (
            target_frequency
            + bandwidth
        )

        mask = (
            (frequencies >= lower)
            &
            (frequencies <= upper)
        )

        if not np.any(mask):

            return 0.0

        return float(
            np.max(
                magnitude[mask]
            )
        )


    # ========================================================
    # SPECTRAL FEATURES
    # ========================================================

    @staticmethod
    def calculate_spectral_features(
        frequencies: np.ndarray,
        magnitude: np.ndarray,
    ):
        """
        Calculate dominant frequency and spectral centroid.
        """

        if len(magnitude) == 0:

            return 0.0, 0.0

        dominant_index = int(
            np.argmax(magnitude)
        )

        dominant_frequency = float(
            frequencies[
                dominant_index
            ]
        )

        magnitude_sum = float(
            np.sum(magnitude)
        )

        if magnitude_sum <= 0:

            spectral_centroid = 0.0

        else:

            spectral_centroid = float(
                np.sum(
                    frequencies
                    * magnitude
                )
                / magnitude_sum
            )

        return (
            dominant_frequency,
            spectral_centroid,
        )


    # ========================================================
    # TIME-DOMAIN FEATURES
    # ========================================================

    @staticmethod
    def calculate_time_features(
        signal: np.ndarray,
    ):
        """
        Calculate RMS, peak and crest factor.
        """

        if len(signal) == 0:

            return 0.0, 0.0, 0.0

        rms = float(
            np.sqrt(
                np.mean(
                    signal ** 2
                )
            )
        )

        peak = float(
            np.max(
                np.abs(signal)
            )
        )

        if rms > 0:

            crest_factor = (
                peak / rms
            )

        else:

            crest_factor = 0.0

        return (
            rms,
            peak,
            crest_factor,
        )


    # ========================================================
    # MAIN CALCULATION
    # ========================================================

    def calculate(
        self,
        rpm: float,
        wear_index: float = 0.0,
        fault_state: dict | None = None,
    ) -> VibrationState:
        """
        Generate vibration signal and extract diagnostic
        features.
        """

        rpm = max(
            0.0,
            rpm
        )

        rotational_frequency = (
            self.rpm_to_frequency(
                rpm
            )
        )

        # ----------------------------------------------------
        # Generate signal
        # ----------------------------------------------------

        signal = (
            self.generate_signal(
                rpm=rpm,
                wear_index=wear_index,
                fault_state=fault_state,
            )
        )

        # ----------------------------------------------------
        # FFT
        # ----------------------------------------------------

        frequencies, magnitude = (
            self.calculate_fft(
                signal
            )
        )

        # ----------------------------------------------------
        # Time features
        # ----------------------------------------------------

        (
            rms,
            peak,
            crest_factor,
        ) = self.calculate_time_features(
            signal
        )

        # ----------------------------------------------------
        # Spectral features
        # ----------------------------------------------------

        (
            dominant_frequency,
            spectral_centroid,
        ) = self.calculate_spectral_features(
            frequencies,
            magnitude,
        )

        # ----------------------------------------------------
        # Engine orders
        # ----------------------------------------------------

        order_0_5x = (
            self.extract_order_amplitude(
                frequencies,
                magnitude,
                rotational_frequency,
                0.5,
            )
        )

        order_1x = (
            self.extract_order_amplitude(
                frequencies,
                magnitude,
                rotational_frequency,
                1.0,
            )
        )

        order_2x = (
            self.extract_order_amplitude(
                frequencies,
                magnitude,
                rotational_frequency,
                2.0,
            )
        )

        return VibrationState(

            rpm=rpm,

            rotational_frequency_hz=(
                rotational_frequency
            ),

            sample_rate_hz=(
                self.sample_rate_hz
            ),

            signal_rms=rms,

            signal_peak=peak,

            crest_factor=crest_factor,

            dominant_frequency_hz=(
                dominant_frequency
            ),

            spectral_centroid_hz=(
                spectral_centroid
            ),

            order_0_5x=order_0_5x,

            order_1x=order_1x,

            order_2x=order_2x,

            time_signal=signal,
        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    vibration_model = (
        EngineVibrationModel(
            sample_rate_hz=1000.0,
            window_seconds=1.0,
        )
    )

    rpm = 4000.0

    print(
        "\nAERIS-TWIN VIBRATION MODEL"
    )

    print(
        "=" * 90
    )

    # --------------------------------------------------------
    # Normal condition
    # --------------------------------------------------------

    normal = (
        vibration_model.calculate(
            rpm=rpm,
            wear_index=0.10,
        )
    )

    print(
        "\nNORMAL"
    )

    print(
        f"RPM: "
        f"{normal.rpm:.0f}"
    )

    print(
        f"Rotational frequency: "
        f"{normal.rotational_frequency_hz:.2f} Hz"
    )

    print(
        f"RMS: "
        f"{normal.signal_rms:.4f}"
    )

    print(
        f"Peak: "
        f"{normal.signal_peak:.4f}"
    )

    print(
        f"Crest factor: "
        f"{normal.crest_factor:.3f}"
    )

    print(
        f"Dominant frequency: "
        f"{normal.dominant_frequency_hz:.2f} Hz"
    )

    print(
        f"Spectral centroid: "
        f"{normal.spectral_centroid_hz:.2f} Hz"
    )

    print(
        f"0.5X: "
        f"{normal.order_0_5x:.4f}"
    )

    print(
        f"1X: "
        f"{normal.order_1x:.4f}"
    )

    print(
        f"2X: "
        f"{normal.order_2x:.4f}"
    )

    # --------------------------------------------------------
    # Misfire
    # --------------------------------------------------------

    misfire = (
        vibration_model.calculate(

            rpm=rpm,

            wear_index=0.10,

            fault_state={
                "type":
                    "MISFIRE",

                "severity":
                    0.90,
            },
        )
    )

    print(
        "\nMISFIRE"
    )

    print(
        f"RMS: "
        f"{misfire.signal_rms:.4f}"
    )

    print(
        f"Peak: "
        f"{misfire.signal_peak:.4f}"
    )

    print(
        f"Crest factor: "
        f"{misfire.crest_factor:.3f}"
    )

    print(
        f"0.5X: "
        f"{misfire.order_0_5x:.4f}"
    )

    print(
        f"1X: "
        f"{misfire.order_1x:.4f}"
    )

    print(
        f"2X: "
        f"{misfire.order_2x:.4f}"
    )

    # --------------------------------------------------------
    # Combustion instability
    # --------------------------------------------------------

    instability = (
        vibration_model.calculate(

            rpm=rpm,

            wear_index=0.10,

            fault_state={
                "type":
                    "COMBUSTION_INSTABILITY",

                "severity":
                    0.90,
            },
        )
    )

    print(
        "\nCOMBUSTION INSTABILITY"
    )

    print(
        f"RMS: "
        f"{instability.signal_rms:.4f}"
    )

    print(
        f"Peak: "
        f"{instability.signal_peak:.4f}"
    )

    print(
        f"2X: "
        f"{instability.order_2x:.4f}"
    )