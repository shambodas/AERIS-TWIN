"""Thermal diagnostics module to separate cooling_degradation conditions from mechanical fault classifications."""

from config.engine_config import EngineConfig

class ThermalDiagnostics:
    def __init__(self):
        self.config = EngineConfig()

    def process(self, history: list[dict]) -> str:
        """
        Evaluate thermal history and determine current thermal condition.
        Returns one of: "CRITICAL", "WARNING", "TREND", "NORMAL"
        """
        if not history:
            return "NORMAL"
        
        current = history[-1]
        
        cht = max(
            float(current.get("cht_cylinder_1_c", 0.0) or 0.0),
            float(current.get("cht_cylinder_2_c", 0.0) or 0.0),
            float(current.get("cht_cylinder_3_c", 0.0) or 0.0),
            float(current.get("cht_cylinder_4_c", 0.0) or 0.0)
        )
        oil_temp = float(current.get("oil_temperature_c", 0.0) or 0.0)
        
        if cht >= self.config.cht_limit_red_c or oil_temp >= self.config.oil_limit_c:
            return "CRITICAL"
            
        if cht >= self.config.cht_limit_yellow_c:
            return "WARNING"
            
        if len(history) >= 100:
            past = history[0]
            past_cht = max(
                float(past.get("cht_cylinder_1_c", 0.0) or 0.0),
                float(past.get("cht_cylinder_2_c", 0.0) or 0.0),
                float(past.get("cht_cylinder_3_c", 0.0) or 0.0),
                float(past.get("cht_cylinder_4_c", 0.0) or 0.0)
            )
            dt = current.get("time_s", 0.0) - past.get("time_s", 0.0)
            if dt > 0:
                trend = (cht - past_cht) / dt
                if trend > 0.5 and cht > 90.0:  # Rising rapidly at elevated temperature
                    return "TREND"
                    
        return "NORMAL"

    def get_trend_direction(self, history: list[dict]) -> str:
        """Returns the trend direction based on CHT history."""
        if len(history) >= 100:
            current = history[-1]
            past = history[0]
            cht = max(
                float(current.get("cht_cylinder_1_c", 0.0) or 0.0),
                float(current.get("cht_cylinder_2_c", 0.0) or 0.0),
                float(current.get("cht_cylinder_3_c", 0.0) or 0.0),
                float(current.get("cht_cylinder_4_c", 0.0) or 0.0)
            )
            past_cht = max(
                float(past.get("cht_cylinder_1_c", 0.0) or 0.0),
                float(past.get("cht_cylinder_2_c", 0.0) or 0.0),
                float(past.get("cht_cylinder_3_c", 0.0) or 0.0),
                float(past.get("cht_cylinder_4_c", 0.0) or 0.0)
            )
            dt = current.get("time_s", 0.0) - past.get("time_s", 0.0)
            if dt > 0:
                slope = (cht - past_cht) / dt
                if slope > 0.5:
                    return "increasing"
                if slope < -0.5:
                    return "decreasing"
        return "stable"
