from __future__ import annotations
import socket

import pytest

from tests.conftest import NetworkDisabledError


def test_real_socket_connect_is_blocked():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(NetworkDisabledError):
            s.connect(("example.com", 80))
    finally:
        s.close()


def test_real_socket_connect_ex_is_blocked():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(NetworkDisabledError):
            s.connect_ex(("example.com", 80))
    finally:
        s.close()
