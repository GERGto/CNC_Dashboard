from __future__ import annotations

import os

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows development environment
    fcntl = None


I2C_SLAVE = 0x0703


class I2CError(RuntimeError):
    pass


class LinuxI2CDevice:
    def __init__(self, bus_number, address):
        self.bus_number = int(bus_number)
        self.address = int(address)
        self.path = f"/dev/i2c-{self.bus_number}"

    def is_supported(self):
        return os.name == "posix" and fcntl is not None

    def is_available(self):
        return self.is_supported() and os.path.exists(self.path)

    def write(self, payload):
        self.transfer(write_bytes=payload)

    def read(self, read_length):
        return self.transfer(read_length=read_length)

    def transfer(self, write_bytes=None, read_length=0):
        if not self.is_supported():
            raise I2CError("Linux-I2C ist auf diesem System nicht verfuegbar.")
        if not os.path.exists(self.path):
            raise I2CError(f"I2C-Bus nicht gefunden: {self.path}")

        try:
            with open(self.path, "r+b", buffering=0) as handle:
                fcntl.ioctl(handle.fileno(), I2C_SLAVE, self.address)
                if write_bytes:
                    handle.write(bytes(write_bytes))
                if read_length:
                    data = handle.read(int(read_length))
                    if len(data) != int(read_length):
                        raise I2CError(
                            f"Unvollstaendige I2C-Antwort von {self.path}: "
                            f"{len(data)} statt {read_length} Byte."
                        )
                    return data
                return b""
        except OSError as exc:
            raise I2CError(f"I2C-Zugriff auf {self.path} fehlgeschlagen: {exc}") from exc
