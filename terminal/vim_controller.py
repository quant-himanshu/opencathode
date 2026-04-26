
import sys
import tty
import termios
import time
from typing import Optional, Callable

class VimController:
    """
    Full Vim-inspired state machine for OpenCATHODE.

    Modes:
      NORMAL  — navigate, inspect
      INSERT  — charging mode (i = start charge)
      COMMAND — :optimize, :diff, :passport, :stress-test
      VISUAL  — select time range for causal replay

    Key bindings:
      i        — start charging
      d        — start discharging
      Esc      — return to normal
      :        — enter command mode
      s        — show status
      p        — generate EU passport
      r        — reset cell
      q        — quit
      gg       — go to cycle 1
      G        — go to latest cycle
    """
    MODE_NORMAL  = "NORMAL"
    MODE_INSERT  = "INSERT"
    MODE_COMMAND = "COMMAND"
    MODE_VISUAL  = "VISUAL"

    def __init__(self):
        self.mode = self.MODE_NORMAL
        self.command_buf = ""
        self.pending_g = False
        self.running = True
        self.action = None
        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)

    def _getch(self):
        try:
            tty.setraw(self.fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
        return ch

    def poll(self):
        """Non-blocking key poll. Returns action string or None."""
        import select
        if not select.select([sys.stdin], [], [], 0)[0]:
            return None
        ch = self._getch()
        return self._handle_key(ch)

    def _handle_key(self, ch):
        if self.mode == self.MODE_NORMAL:
            return self._normal_mode(ch)
        elif self.mode == self.MODE_INSERT:
            return self._insert_mode(ch)
        elif self.mode == self.MODE_COMMAND:
            return self._command_mode(ch)
        return None

    def _normal_mode(self, ch):
        if ch == "i":
            self.mode = self.MODE_INSERT
            return "charge_start"
        elif ch == "d":
            return "discharge_start"
        elif ch == "s":
            return "show_status"
        elif ch == "p":
            return "show_passport"
        elif ch == "r":
            return "reset"
        elif ch == ":":
            self.mode = self.MODE_COMMAND
            self.command_buf = ""
            return "command_mode"
        elif ch == "q":
            self.running = False
            return "quit"
        elif ch == "g":
            if self.pending_g:
                self.pending_g = False
                return "goto_start"
            self.pending_g = True
        elif ch == "G":
            return "goto_end"
        elif ch == "":
            self.mode = self.MODE_NORMAL
        return None

    def _insert_mode(self, ch):
        if ch == "":
            self.mode = self.MODE_NORMAL
            return "charge_stop"
        return None

    def _command_mode(self, ch):
        if ch == "" or ch == "
":
            cmd = self.command_buf.strip()
            self.command_buf = ""
            self.mode = self.MODE_NORMAL
            return f"cmd:{cmd}"
        elif ch == "":
            self.mode = self.MODE_NORMAL
            self.command_buf = ""
            return None
        elif ch == "":
            self.command_buf = self.command_buf[:-1]
        else:
            self.command_buf += ch
        return f"typing:{self.command_buf}"

    def cleanup(self):
        try:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
        except Exception:
            pass
