import os
import sys
import threading
import asyncio
import tkinter as tk
from PIL import Image, ImageTk

try:
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus
    WINRT_AVAILABLE = True
except ImportError:
    WINRT_AVAILABLE = False

# ---------- PALETA ----------
TRANSPARENT = "#ff00ff"
WHITE = "#ffffff"
BLACK = "#111111"
YELLOW = "#ffff00"
CYAN = "#00ffff"
GREEN = "#00ff00"
RED = "#ff5555"
ORANGE = "#ffaa00"
FONT = ("Consolas", 9, "bold")


def pixel_label(parent, text, fg=WHITE, size=9):
    return tk.Label(parent, text=text, font=("Consolas", size, "bold"),
                    bg=BLACK, fg=fg, justify="center")


def pixel_button(parent, text, command, color=CYAN):
    return tk.Button(parent, text=text, command=command, font=FONT,
                     bg=BLACK, fg=color, activebackground=color,
                     activeforeground="#000000", bd=0, relief="flat",
                     highlightthickness=0, cursor="hand2", padx=6, pady=2)


class PixelBubble:
    PX = 4        
    ARROW = 16    
    PAD = 8       
    GAP = -6      

    def __init__(self, pet):
        self.pet = pet
        self.win = None
        self.canvas = None
        self.content = None
        self._state = None

    @property
    def is_open(self):
        return self.win is not None and self.win.winfo_exists()

    def close(self):
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        self.win = None
        self._state = None

    def show(self, builder):
        self.close()
        self.win = tk.Toplevel(self.pet.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", not self.pet.hidden)
        self.win.config(bg=TRANSPARENT)
        self.win.wm_attributes("-transparentcolor", TRANSPARENT)

        self.canvas = tk.Canvas(self.win, bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.content = tk.Frame(self.canvas, bg=BLACK)
        builder(self.content)
        self.content.update_idletasks()

        inner = self.PX + self.PAD
        self.box_w = self.content.winfo_reqwidth() + 2 * inner
        self.box_h = max(self.content.winfo_reqheight() + 2 * inner, self.PX * 12)
        self.W = self.ARROW + self.box_w
        self.H = self.box_h
        self.canvas.config(width=self.W, height=self.H)
        self.canvas.create_window(0, 0, window=self.content, anchor="center", tags="content")

        self._state = None
        self.reposition()
        if self.pet.hidden:
            self.win.lower()

    def reposition(self):
        if not self.is_open:
            return
        root = self.pet.root
        root.update_idletasks()
        pet_x, pet_y = root.winfo_x(), root.winfo_y()
        pet_w, pet_h = root.winfo_width(), root.winfo_height()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()

        side = "right"
        x = pet_x + pet_w + self.GAP
        if x + self.W > sw:                      
            side = "left"
            x = pet_x - self.W - self.GAP

        y = pet_y + pet_h // 2 - self.H // 2      
        y = max(0, min(y, sh - self.H - 40))

        low, high = self.PX * 5, self.H - self.PX * 5
        arrow_cy = max(low, min(pet_y + pet_h // 2 - y, high))

        state = (side, arrow_cy)
        if state != self._state:
            self._draw(side, arrow_cy)
            self._state = state
        self.win.geometry(f"+{x}+{y}")

    def _draw(self, side, cy):
        c, px, A, W, H = self.canvas, self.PX, self.ARROW, self.W, self.H
        flip = (side == "left")
        c.delete("bg")

        def rect(x0, y0, x1, y1, color):
            if flip:
                x0, x1 = W - x1, W - x0
            c.create_rectangle(x0, y0, x1, y1, fill=color, outline="", tags="bg")

        def box(x0, y0, x1, y1, color):         
            rect(x0 + px, y0, x1 - px, y1, color)
            rect(x0, y0 + px, x1, y1 - px, color)

        for i in range(4):
            half = i * px + px // 2
            rect(i * px, cy - half, A + px, cy + half, WHITE)
        box(A, 0, W, H, WHITE)                    
        box(A + px, px, W - px, H - px, BLACK)    
        for j in range(3):
            half = j * px + px // 2
            rect((j + 1) * px, cy - half, A + px * 2, cy + half, BLACK)

        c.tag_lower("bg")
        cx = A + self.box_w / 2
        if flip:
            cx = W - cx
        c.coords("content", cx, H / 2)


class DesktopPetAssistant:
    def __init__(self, root, gif_path):
        self.root = root

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.config(bg=TRANSPARENT)
        self.root.wm_attributes("-transparentcolor", TRANSPARENT)

        self.is_monitoring = False
        self.awake_active = False
        self.awake_left = 0
        self.lbl_count = None
        self.hidden = False                  
        self.has_dragged = False
        self.bubble = PixelBubble(self)

        self.frames = []
        try:
            im = Image.open(gif_path)
            while True:
                self.frames.append(ImageTk.PhotoImage(im.copy().convert("RGBA")))
                im.seek(len(self.frames))
        except EOFError:
            pass
        self.current_frame = 0


        self.lbl_pet = tk.Label(self.root, image=self.frames[0], bg=TRANSPARENT, bd=0)
        self.lbl_pet.pack()


        self.lbl_pet.bind("<ButtonPress-1>", self.on_left_click_press)
        self.lbl_pet.bind("<B1-Motion>", self.do_drag)
        self.lbl_pet.bind("<ButtonRelease-1>", self.on_left_click_release)
        self.lbl_pet.bind("<Button-3>", self.show_right_click_menu)


        self.right_menu = tk.Menu(
            self.root, tearoff=0, bg=BLACK, fg=WHITE,
            activebackground=WHITE, activeforeground="#000000",
            font=("Consolas", 10, "bold"), bd=3, relief="flat"
        )
        self.right_menu.add_command(label="Ocultarse (al fondo)", command=self.toggle_hide)
        self.right_menu.add_command(label="Cancelar Apagado", command=self.cancel_shutdown)
        self.right_menu.add_separator()
        self.right_menu.add_command(label="Cerrar Asistente", command=self.root.quit)


        pet_w, pet_h = self.frames[0].width(), self.frames[0].height()
        pos_x = self.root.winfo_screenwidth() - pet_w - 300
        pos_y = self.root.winfo_screenheight() - pet_h - 120
        self.root.geometry(f"+{pos_x}+{pos_y}")

        self.animate()


    def animate(self):
        if self.frames:
            self.current_frame = (self.current_frame + 1) % len(self.frames)
            self.lbl_pet.configure(image=self.frames[self.current_frame])
        self.root.after(100, self.animate)


    def on_left_click_press(self, event):
        self.off_x = event.x_root - self.root.winfo_x()
        self.off_y = event.y_root - self.root.winfo_y()
        self.press_x, self.press_y = event.x_root, event.y_root
        self.has_dragged = False

    def do_drag(self, event):
        if not self.has_dragged:
            if abs(event.x_root - self.press_x) + abs(event.y_root - self.press_y) < 4:
                return                       
            self.has_dragged = True
        self.root.geometry(f"+{event.x_root - self.off_x}+{event.y_root - self.off_y}")
        self.bubble.reposition()

    def on_left_click_release(self, event):
        if not self.has_dragged:
            self.toggle_speech_bubble()
        if self.hidden:
            self._send_to_back()             

    def toggle_speech_bubble(self):
        if self.awake_active:                
            return
        if self.bubble.is_open:
            self.bubble.close()
        else:
            self.show_menu()

    def show_menu(self):
        def build(f):
            pixel_label(f, "> OPCIONES <", YELLOW).pack(pady=(0, 6))
            pixel_button(f, "[ TEMPORIZADOR ]", self.show_timer_page, CYAN).pack(fill="x", pady=2)
            text, color = ("[ DORMIR: ON ]", GREEN) if self.is_monitoring else ("[ DORMIR: OFF ]", RED)
            pixel_button(f, text, self.toggle_sleep_mode, color).pack(fill="x", pady=2)
            pixel_button(f, "[ CANCELAR APAGADO ]", self.cancel_shutdown, ORANGE).pack(fill="x", pady=2)
            pixel_button(f, "[ X ]", self.bubble.close, WHITE).pack(fill="x", pady=(6, 0))
        self.bubble.show(build)

    def show_message(self, text, color=WHITE, on_ok=None):
        def build(f):
            pixel_label(f, text, color).pack(pady=(0, 8))
            pixel_button(f, "[ OK ]", on_ok or self.bubble.close, CYAN).pack()
        self.bubble.show(build)

    def show_timer_page(self):
        self.timer_var = tk.StringVar(value="30")

        def build(f):
            pixel_label(f, "> APAGAR EN <", YELLOW).pack(pady=(0, 6))

            row = tk.Frame(f, bg=BLACK)
            row.pack()
            self.timer_entry = tk.Entry(
                row, textvariable=self.timer_var, width=4, justify="center",
                font=("Consolas", 12, "bold"), bg="#000000", fg=YELLOW,
                insertbackground=WHITE, relief="flat", bd=0,
                highlightthickness=2, highlightbackground=WHITE, highlightcolor=CYAN
            )
            self.timer_entry.pack(side="left")
            self.timer_entry.bind("<Return>", lambda e: self.confirm_timer())
            pixel_label(row, " MIN", WHITE).pack(side="left")

            presets = tk.Frame(f, bg=BLACK)
            presets.pack(pady=6)
            for m in (15, 30, 60, 90):
                pixel_button(presets, str(m), lambda m=m: self.timer_var.set(str(m)), CYAN).pack(side="left", padx=1)

            btns = tk.Frame(f, bg=BLACK)
            btns.pack()
            pixel_button(btns, "[ OK ]", self.confirm_timer, GREEN).pack(side="left", padx=2)
            pixel_button(btns, "[ VOLVER ]", self.show_menu, RED).pack(side="left", padx=2)

        self.bubble.show(build)
        self.root.after(60, self._focus_entry)

    def _focus_entry(self):
        try:
            self.timer_entry.focus_force()
            self.timer_entry.select_range(0, "end")
        except (tk.TclError, AttributeError):
            pass


    def confirm_timer(self):
        try:
            mins = int(self.timer_var.get())
        except ValueError:
            mins = 0
        if not 1 <= mins <= 600:
            self.show_message("ELIGE UN NUMERO\nENTRE 1 Y 600", RED, on_ok=self.show_timer_page)
            return
        if sys.platform == "win32":
            os.system(f"shutdown /s /t {mins * 60}")
        else:
            os.system(f"shutdown -h +{mins}")
        self.show_message(f"LISTO!\nAPAGO EN {mins} MIN", GREEN)

    def cancel_shutdown(self):
        self.awake_active = False            
        if sys.platform == "win32":
            os.system("shutdown /a")
        else:
            os.system("killall shutdown")
        self.show_message("APAGADO\nCANCELADO", ORANGE)

    def shutdown_now(self):
        if sys.platform == "win32":
            os.system("shutdown /s /t 0")
        else:
            os.system("shutdown -h now")

    def _send_to_back(self):
        self.root.lower()
        if self.bubble.is_open:
            self.bubble.win.lower()

    def hide_pet(self):
        self.hidden = True
        self.bubble.close()
        self.root.attributes("-topmost", False)
        self._send_to_back()

    def show_pet(self):
        self.hidden = False
        self.root.attributes("-topmost", True)
        self.root.lift()
        if self.bubble.is_open:
            self.bubble.win.attributes("-topmost", True)
            self.bubble.win.lift()

    def toggle_hide(self):
        if self.awake_active:                
            return
        if self.hidden:
            self.show_pet()
        else:
            self.hide_pet()

    # ---------- CLIC DERECHO ----------
    def show_right_click_menu(self, event):
        if not self.awake_active:
            self.bubble.close()
        label = "Mostrar al frente" if self.hidden else "Ocultarse (al fondo)"
        self.right_menu.entryconfig(0, label=label)
        self.right_menu.tk_popup(event.x_root, event.y_root)

    # ---------- MODO "A DORMIR" ----------
    def toggle_sleep_mode(self):
        if not WINRT_AVAILABLE:
            self.show_message("FALTA LA LIBRERIA\nwinrt-Windows.Media.Control", RED)
            return

        if not self.is_monitoring:
            self.is_monitoring = True
            threading.Thread(target=self.run_async_media_monitor, daemon=True).start()
            self.show_message("MODO DORMIR\nACTIVADO", GREEN)
        else:
            self.is_monitoring = False
            self.show_message("MODO DORMIR\nDESACTIVADO", RED)

    def run_async_media_monitor(self):
        asyncio.run(self.monitor_media_session())

    async def monitor_media_session(self):
        try:
            manager = await MediaManager.request_async()
            was_playing = False

            while self.is_monitoring:
                session = manager.get_current_session()
                if session:
                    playback_info = session.get_playback_info()
                    is_playing = (playback_info.playback_status == PlaybackStatus.PLAYING)

                    if is_playing:
                        was_playing = True
                    elif was_playing and not is_playing:
                        self.is_monitoring = False
                        self.root.after(0, self.ask_if_awake)
                        break

                await asyncio.sleep(2)
        except Exception as e:
            print("Error monitoreando media:", e)

    def ask_if_awake(self):
        self.show_pet()                      
        self.awake_active = True
        self.awake_left = 30

        def build(f):
            pixel_label(f, "> ¿SIGUES AHI? <", YELLOW).pack(pady=(0, 4))
            pixel_label(f, "EL VIDEO TERMINO", WHITE).pack()
            self.lbl_count = pixel_label(f, f"APAGANDO EN {self.awake_left:02d}s", RED)
            self.lbl_count.pack(pady=4)
            pixel_button(f, "[ SIGO DESPIERTO ]", self.im_awake, GREEN).pack(pady=(2, 0))

        self.bubble.show(build)
        self.root.after(1000, self._tick_awake)

    def _tick_awake(self):
        if not self.awake_active:
            return
        self.awake_left -= 1
        if self.awake_left <= 0:
            self.awake_active = False
            self.bubble.close()
            self.shutdown_now()
            return
        try:
            self.lbl_count.configure(text=f"APAGANDO EN {self.awake_left:02d}s")
        except (tk.TclError, AttributeError):
            pass
        self.root.after(1000, self._tick_awake)

    def im_awake(self):
        self.awake_active = False
        self.show_message("GENIAL!\nDISFRUTA TU NOCHE", GREEN)


if __name__ == "__main__":
    root = tk.Tk()
    gif = os.path.join(os.path.dirname(os.path.abspath(__file__)), "racoonpix.gif")
    app = DesktopPetAssistant(root, gif)
    root.mainloop()