"""Suite-wide settings: the product makes no network connection (REQ-083), so the suite blocks the socket layer."""

import socket
import warnings

import pytest

warnings.filterwarnings("ignore")


class NetworkBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True, scope="session")
def _block_network():
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def blocked(self, *a, **k):
        raise NetworkBlocked("network access is blocked in the test suite")

    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    yield
    socket.socket.connect, socket.socket.connect_ex = real_connect, real_connect_ex
