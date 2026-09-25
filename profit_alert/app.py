"""Interface do monitor. Todas as interações com Tk ocorrem na thread principal."""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
import winsound
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from PIL import Image, ImageDraw

from .core import (default_drawdown_cents, format_brl, parse_drawdown_threshold,
                   parse_gain_threshold, parse_threshold)
from .monitor import Monitor, MonitorConfig, MonitorEvent
from .windows import WindowTarget, list_profit_windows


def _configure_tcl_paths() -> None:
    """Evita falhas do Tcl com caminhos Windows contendo espaços."""
    if os.name != "nt":
        return
    base = (Path(sys._MEIPASS) / "tcl" if getattr(sys, "frozen", False)
            else Path(sys.base_prefix) / "tcl")
    for name, folder in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):
        path = base / folder
        if path.is_dir():
            os.environ[name] = "//?/" + path.resolve().as_posix()


def _beep(kind: str = "loss") -> None:
    def play() -> None:
        try:
            if kind == "gain":
                for frequency in (700, 900, 1100):
                    winsound.Beep(frequency, 180)
            else:
                for _ in range(3 if kind == "loss" else 2):
                    winsound.Beep(1250 if kind == "loss" else 650,
                                  350 if kind == "loss" else 220)
        except RuntimeError:
            winsound.MessageBeep(winsound.MB_ICONASTERISK if kind == "gain"
                                 else winsound.MB_ICONEXCLAMATION)

    threading.Thread(target=play, name="ProfitAlertSound", daemon=True).start()


def _tray_image() -> Image.Image:
    image = Image.new("RGB", (64, 64), "#20262e")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((5, 5, 59, 59), radius=13, fill="#b93636")
    draw.text((22, 14), "P", fill="white", stroke_width=1)
    return image


class ProfitAlertApp:
    def __init__(self) -> None:
        _configure_tcl_paths()
        self.root = tk.Tk()
        self.root.title("Leitor Profit · alertas de perda, ganho e drawdown")
        self.root.geometry("820x730")
        self.root.minsize(720, 650)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_or_exit)
        self.events: queue.Queue[MonitorEvent] = queue.Queue()
        self.monitor: Monitor | None = None
        self.tray = None
        self.targets: dict[str, WindowTarget] = {}
        self.window_var = tk.StringVar()
        self.threshold_var = tk.StringVar(value="-150,00")
        self.gain_threshold_var = tk.StringVar(value="")
        default_drawdown = default_drawdown_cents(parse_threshold(self.threshold_var.get()))
        self.drawdown_threshold_var = tk.StringVar(
            value=format_brl(default_drawdown).removeprefix("R$ "))
        self._drawdown_manually_edited = False
        self._updating_drawdown = False
        self.threshold_var.trace_add("write", self._update_drawdown_default)
        self.drawdown_threshold_var.trace_add("write", self._mark_drawdown_edited)
        self.account_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="Automático: acessibilidade, depois OCR")
        self.scan_height_var = tk.StringVar(value="220")
        self.auto_action_var = tk.BooleanVar(value=False)
        self.gain_auto_action_var = tk.BooleanVar(value=False)
        self.drawdown_alert_var = tk.BooleanVar(value=False)
        self.drawdown_auto_action_var = tk.BooleanVar(value=False)
        self.action_var = tk.StringVar(value="Pausar + Zerar: não acionado")
        self.drawdown_state_var = tk.StringVar(value="Drawdown: desativado")
        self.status_var = tk.StringVar(value="Parado")
        self.value_var = tk.StringVar(value="Ainda sem leitura")
        self._build_ui()
        self.refresh_windows()
        self._start_tray()
        self.root.after(150, self._drain_events)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Alertas de perda, ganho e drawdown do Profit",
                  font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Alertas para os limites configurados. O acionamento global do Profit é opcional.").pack(anchor="w", pady=(2, 14))

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Janela do Profit", width=19).pack(side="left")
        self.window_combo = ttk.Combobox(row, textvariable=self.window_var, state="readonly")
        self.window_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Atualizar", command=self.refresh_windows).pack(side="left", padx=(8, 0))

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Limite de perda", width=19).pack(side="left")
        ttk.Entry(row, textvariable=self.threshold_var, width=15).pack(side="left")
        ttk.Label(row, text="Alerta em valor igual ou menor. Ex.: -150,00").pack(side="left", padx=10)

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Limite de ganho", width=19).pack(side="left")
        ttk.Entry(row, textvariable=self.gain_threshold_var, width=15).pack(side="left")
        ttk.Label(row, text="Opcional; alerta em valor igual ou maior. Ex.: 150,00").pack(side="left", padx=10)

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Limite de drawdown", width=19).pack(side="left")
        ttk.Entry(row, textvariable=self.drawdown_threshold_var, width=15).pack(side="left")
        ttk.Label(row, text="Recuo desde o pico positivo. Padrão: 3 × |limite de perda|."
                  ).pack(side="left", padx=10)

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Conta (opcional)", width=19).pack(side="left")
        ttk.Entry(row, textvariable=self.account_var, width=24).pack(side="left")
        ttk.Label(row, text="Informe apenas os dígitos, se quiser conferir a conta.").pack(side="left", padx=10)

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Método", width=19).pack(side="left")
        ttk.Combobox(
            row, textvariable=self.mode_var, state="readonly", width=39,
            values=("Automático: acessibilidade, depois OCR", "Somente acessibilidade", "Somente OCR da janela"),
        ).pack(side="left")

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Altura de leitura OCR", width=19).pack(side="left")
        ttk.Entry(row, textvariable=self.scan_height_var, width=8).pack(side="left")
        ttk.Label(row, text="pixels do topo; ajuste se o campo não for encontrado.").pack(side="left", padx=10)

        self.auto_checkbox = ttk.Checkbutton(
            frame, text="Acionar Pausar + Zerar posições no limite de perda",
            variable=self.auto_action_var)
        self.auto_checkbox.pack(anchor="w", pady=(10, 0))
        self.gain_auto_checkbox = ttk.Checkbutton(
            frame, text="Acionar Pausar + Zerar posições no limite de ganho",
            variable=self.gain_auto_action_var, command=self._validate_gain_action_selection)
        self.gain_auto_checkbox.pack(anchor="w")
        self.drawdown_alert_checkbox = ttk.Checkbutton(
            frame, text="Alerta de drawdown",
            variable=self.drawdown_alert_var,
            command=lambda: self._validate_drawdown_selection(self.drawdown_alert_var))
        self.drawdown_alert_checkbox.pack(anchor="w", pady=(6, 0))
        self.drawdown_auto_checkbox = ttk.Checkbutton(
            frame, text="Acionar Pausar + Zerar posições no drawdown",
            variable=self.drawdown_auto_action_var,
            command=lambda: self._validate_drawdown_selection(self.drawdown_auto_action_var))
        self.drawdown_auto_checkbox.pack(anchor="w")
        ttk.Label(frame, text="Ação em TODAS AS CONTAS. Perda e ganho compartilham uma tentativa diária; "
                  "drawdown tem uma própria.", wraplength=760).pack(anchor="w", pady=(0, 4))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(12, 10))
        self.start_button = ttk.Button(buttons, text="Iniciar monitoramento", command=self.start_monitor)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Parar", command=self.stop_monitor, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(buttons, text="Testar som perda", command=_beep).pack(side="left", padx=8)
        ttk.Button(buttons, text="Testar som ganho", command=lambda: _beep("gain")).pack(side="left")

        status = ttk.LabelFrame(frame, text="Estado", padding=10)
        status.pack(fill="x", pady=(2, 10))
        ttk.Label(status, textvariable=self.status_var, wraplength=640).pack(anchor="w")
        ttk.Label(status, textvariable=self.value_var, font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(5, 0))
        ttk.Label(status, textvariable=self.drawdown_state_var, wraplength=700).pack(anchor="w", pady=(4, 0))
        ttk.Label(status, textvariable=self.action_var, wraplength=680).pack(anchor="w", pady=(4, 0))

        ttk.Label(frame, text="Eventos desta sessão").pack(anchor="w")
        self.log = scrolledtext.ScrolledText(frame, height=8, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)
        self._log("Escolha a janela do Profit e inicie. Pode deixar Chrome ou VS Code por cima.")

    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"{datetime.now():%H:%M:%S}  {message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh_windows(self) -> None:
        previous = self.window_var.get()
        found = list_profit_windows()
        if not found:
            self.status_var.set("Nenhuma janela principal do Profit Pro encontrada. Abra o Profit e clique em Atualizar.")
            self._log("Nenhuma janela principal do Profit Pro encontrada.")
        self.targets = {target.label: target for target in found}
        self.window_combo.configure(values=list(self.targets))
        if previous in self.targets:
            self.window_var.set(previous)
        elif found:
            self.window_var.set(found[0].label)
        else:
            self.window_var.set("")

    def _update_drawdown_default(self, *_args) -> None:
        if self._drawdown_manually_edited:
            return
        try:
            loss_cents = parse_threshold(self.threshold_var.get())
        except ValueError:
            return
        default = format_brl(default_drawdown_cents(loss_cents)).removeprefix("R$ ")
        if self.drawdown_threshold_var.get() != default:
            self._updating_drawdown = True
            try:
                self.drawdown_threshold_var.set(default)
            finally:
                self._updating_drawdown = False

    def _mark_drawdown_edited(self, *_args) -> None:
        if not self._updating_drawdown:
            self._drawdown_manually_edited = True

    def _validate_drawdown_selection(self, selected_var: tk.BooleanVar) -> None:
        if not selected_var.get():
            return
        try:
            if parse_drawdown_threshold(self.drawdown_threshold_var.get()) is None:
                raise ValueError("Informe o limite de drawdown antes de ativar esta opção.")
        except ValueError as exc:
            selected_var.set(False)
            messagebox.showerror("Leitor Profit", str(exc))

    def _validate_gain_action_selection(self) -> None:
        if not self.gain_auto_action_var.get():
            return
        try:
            if parse_gain_threshold(self.gain_threshold_var.get()) is None:
                raise ValueError("Informe o limite de ganho antes de marcar o acionamento automático de ganho.")
        except ValueError as exc:
            self.gain_auto_action_var.set(False)
            messagebox.showerror("Leitor Profit", str(exc))

    def start_monitor(self) -> None:
        target = self.targets.get(self.window_var.get())
        if target is None:
            messagebox.showerror("Leitor Profit", "Selecione uma janela do Profit.")
            return
        try:
            threshold = parse_threshold(self.threshold_var.get())
            gain_threshold = parse_gain_threshold(self.gain_threshold_var.get())
            drawdown_threshold = parse_drawdown_threshold(self.drawdown_threshold_var.get())
            if self.gain_auto_action_var.get() and gain_threshold is None:
                raise ValueError("Informe o limite de ganho para usar o acionamento automático de ganho.")
            if (self.drawdown_alert_var.get() or self.drawdown_auto_action_var.get()) and drawdown_threshold is None:
                raise ValueError("Informe o limite de drawdown para usar o alerta ou acionamento automático.")
            scan_height = int(self.scan_height_var.get())
            if not 140 <= scan_height <= 500:
                raise ValueError("A altura de leitura deve ficar entre 140 e 500 pixels.")
            account = self.account_var.get().strip()
            if account and not account.isdecimal():
                raise ValueError("Informe apenas os dígitos do número da conta.")
        except ValueError as exc:
            messagebox.showerror("Leitor Profit", str(exc))
            return
        mode = {
            "Automático: acessibilidade, depois OCR": "auto",
            "Somente acessibilidade": "uia",
            "Somente OCR da janela": "ocr",
        }[self.mode_var.get()]
        loss_action = self.auto_action_var.get()
        gain_action = self.gain_auto_action_var.get()
        drawdown_alert = self.drawdown_alert_var.get()
        drawdown_action = self.drawdown_auto_action_var.get()
        automatic = loss_action or gain_action or drawdown_action
        self.monitor = Monitor(MonitorConfig(
            hwnd=target.hwnd, threshold_cents=threshold, mode=mode,
            expected_account=account, scan_height=scan_height,
            auto_action=loss_action, pid=target.pid,
            gain_threshold_cents=gain_threshold, gain_auto_action=gain_action,
            drawdown_threshold_cents=drawdown_threshold,
            drawdown_alert=drawdown_alert, drawdown_auto_action=drawdown_action,
        ), self.events)
        self.monitor.start()
        action_limits = " e ".join(name for name, enabled in (
            ("perda", loss_action), ("ganho", gain_action),
            ("drawdown", drawdown_action)) if enabled)
        self.action_var.set(f"Pausar + Zerar: aguardando cruzamento ({action_limits})" if automatic
                            else "Pausar + Zerar: não acionado")
        self.drawdown_state_var.set("Drawdown: aguardando pico positivo" if (
            drawdown_alert or drawdown_action) else "Drawdown: desativado")
        self.status_var.set("Iniciando...")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.auto_checkbox.configure(state="disabled")
        self.gain_auto_checkbox.configure(state="disabled")
        self.drawdown_alert_checkbox.configure(state="disabled")
        self.drawdown_auto_checkbox.configure(state="disabled")
        gain_label = format_brl(gain_threshold) if gain_threshold is not None else "desligado"
        drawdown_label = format_brl(drawdown_threshold) if drawdown_threshold is not None else "desligado"
        self._log(f"Iniciado: {target.title} | perda {format_brl(threshold)} | ganho {gain_label} | "
                  f"drawdown {drawdown_label} ({'alerta' if drawdown_alert else 'sem alerta'}) | método "
                  f"{'OCR para ação automática' if automatic else mode} | "
                  f"ação global {action_limits if automatic else 'desligada'}")

    def stop_monitor(self) -> None:
        if self.monitor is not None:
            self.monitor.stop()
        self.status_var.set("Parando...")

    def _show_notice(self, title: str, message: str, kind: str) -> None:
        _beep(kind)
        popup = tk.Toplevel(self.root)
        popup.title(title)
        popup.attributes("-topmost", True)
        popup.resizable(False, False)
        popup.configure(bg={"loss": "#822626", "gain": "#246b45",
                            "drawdown": "#6c511c"}.get(kind, "#6c511c"))
        label = tk.Label(popup, text=title, font=("Segoe UI", 16, "bold"), fg="white", bg=popup["bg"])
        label.pack(padx=22, pady=(20, 7))
        tk.Label(popup, text=message, font=("Segoe UI", 12), fg="white", bg=popup["bg"], wraplength=460).pack(padx=22)
        tk.Button(popup, text="Entendi", command=popup.destroy, width=14).pack(pady=18)
        popup.update_idletasks()
        x = max(0, popup.winfo_screenwidth() - popup.winfo_width() - 30)
        popup.geometry(f"+{x}+40")
        popup.lift()

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event.kind == "reading" and event.reading is not None:
                    when = datetime.fromtimestamp(event.reading.captured_at)
                    self.value_var.set(f"{format_brl(event.reading.cents)}  ·  {event.reading.source}  ·  {when:%H:%M:%S}")
                elif event.kind == "status":
                    self.status_var.set(event.message)
                    self._log(event.message)
                elif event.kind == "alert":
                    self.status_var.set(event.message)
                    self._log(event.message)
                    self._show_notice("LIMITE DE PERDA ATINGIDO", event.message + "\nConfira e aja no Profit.", "loss")
                elif event.kind == "gain_alert":
                    self.status_var.set(event.message)
                    self._log(event.message)
                    self._show_notice("LIMITE DE GANHO ATINGIDO", event.message + "\nConfira o Profit.", "gain")
                elif event.kind == "drawdown_state":
                    self.drawdown_state_var.set(event.message)
                elif event.kind == "drawdown_alert":
                    self.status_var.set(event.message)
                    self._log(event.message)
                    self._show_notice("LIMITE DE DRAWDOWN ATINGIDO", event.message +
                                      "\nConfira o Profit.", "drawdown")
                elif event.kind == "action":
                    self.action_var.set("Pausar + Zerar: " + event.message)
                    self._log(event.message)
                elif event.kind == "action_failed":
                    self.action_var.set("Pausar + Zerar: " + event.message)
                    self._log(event.message)
                    self._show_notice("FALHA NO ZERAMENTO AUTOMÁTICO", event.message +
                                      "\nConfira o Profit manualmente.", "warning")
                elif event.kind == "warning":
                    self.status_var.set("ATENÇÃO: " + event.message)
                    self._log("ATENÇÃO: " + event.message)
                    self._show_notice("LEITURA DO PROFIT INDISPONÍVEL", event.message, "warning")
                elif event.kind == "stopped":
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.auto_checkbox.configure(state="normal")
                    self.gain_auto_checkbox.configure(state="normal")
                    self.drawdown_alert_checkbox.configure(state="normal")
                    self.drawdown_auto_checkbox.configure(state="normal")
                    self._log(event.message)
        except queue.Empty:
            pass
        self.root.after(150, self._drain_events)

    def _start_tray(self) -> None:
        try:
            import pystray

            self.tray = pystray.Icon(
                "LeitorProfit", _tray_image(), "Leitor Profit",
                menu=pystray.Menu(
                    pystray.MenuItem("Mostrar", lambda _icon, _item: self.root.after(0, self.show)),
                    pystray.MenuItem("Sair", lambda _icon, _item: self.root.after(0, self.exit)),
                ),
            )
            self.tray.run_detached()
        except Exception as exc:
            self.tray = None
            self._log(f"Ícone da bandeja indisponível: {exc}. Fechar encerrará o aplicativo.")

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def hide_or_exit(self) -> None:
        if self.tray is None:
            self.exit()
        else:
            self.root.withdraw()

    def exit(self) -> None:
        if self.monitor is not None:
            self.monitor.stop()
            if self.monitor.thread is not None:
                self.monitor.thread.join(timeout=3)
        if self.tray is not None:
            self.tray.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
