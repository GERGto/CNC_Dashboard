import unittest

from cnc_hardware.pcf8574_inputs import PCF8574InputModule


class FakeI2CDevice:
    path = "/dev/i2c-fake"

    def __init__(self, raw_value):
        self.raw_value = raw_value
        self.writes = []

    @staticmethod
    def is_supported():
        return True

    @staticmethod
    def is_available():
        return True

    def write(self, payload):
        self.writes.append(tuple(payload))

    def read(self, length):
        return bytes([self.raw_value & 0xFF])[:length]


class PCF8574InputModuleTests(unittest.TestCase):
    def test_spindle_running_defaults_to_active_high_while_estop_stays_active_low(self):
        module = PCF8574InputModule(
            enabled=True,
            active_low=True,
            hardware_estop_channels=(1, 2),
            spindle_running_channels=(3,),
        )
        module.device = FakeI2CDevice(0b00000111)

        snapshot = module.read_snapshot()

        self.assertTrue(snapshot["spindleRunning"])
        self.assertEqual(snapshot["spindleRunningInputIds"], ["input3"])
        self.assertFalse(snapshot["hardwareEStopEngaged"])
        self.assertFalse(snapshot["channels"]["input1"]["active"])
        self.assertFalse(snapshot["channels"]["input2"]["active"])
        self.assertTrue(snapshot["channels"]["input3"]["active"])
        self.assertFalse(snapshot["channels"]["input3"]["activeLow"])

    def test_spindle_running_inactive_when_input_three_is_low_by_default(self):
        module = PCF8574InputModule(
            enabled=True,
            active_low=True,
            hardware_estop_channels=(1, 2),
            spindle_running_channels=(3,),
        )
        module.device = FakeI2CDevice(0b00000011)

        snapshot = module.read_snapshot()

        self.assertFalse(snapshot["spindleRunning"])
        self.assertEqual(snapshot["spindleRunningInputIds"], [])


if __name__ == "__main__":
    unittest.main()
