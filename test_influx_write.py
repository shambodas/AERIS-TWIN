from database.influx_writer import InfluxWriter


def run_influx_write_test():
    writer = InfluxWriter()
    test_telemetry = {
        "rpm": 4500.0,
        "manifold_pressure_kpa": 85.0,
        "fuel_flow_kg_s": 0.012,
        "cht_cylinder_1_c": 180.0,
        "cht_cylinder_2_c": 182.0,
        "oil_temperature_c": 95.0,
        "oil_pressure_psi": 55.0,
        "battery_voltage_v": 24.5,
        "vibration_rms": 0.8,
    }
    writer.write_telemetry(test_telemetry)
    print("Test telemetry written successfully!")
    writer.close()


if __name__ == "__main__":
    run_influx_write_test()
