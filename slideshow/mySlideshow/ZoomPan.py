import tkinter as tk
from PIL import Image, ImageTk


class ZoomPan:
    """Interactive zoom & pan helper for a Tk image widget (Label or Canvas).

    Contain (no upscale) mode: smaller images are not enlarged to fill screen.
    Set allow_upscale=True to allow enlarging small images.

    Zoom model: scale-first then crop. As you zoom in, image expands into any
    letterbox bars before cropping further, producing smooth expected behavior
    on ultra-wide displays.
    """

    def __init__(self, widget: tk.Widget, screen_w: int, screen_h: int, on_image_changed=None, allow_upscale: bool = False):
        self.widget = widget
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.on_image_changed = on_image_changed
        self.allow_upscale = allow_upscale

        # Original image & sizing
        self.orig_image = None
        self.fit_image = None  # image scaled by base_scale (no crop) for zoom_factor==1 display

        # Zoom state
        self.base_scale = 1.0      # scale to fit (or 1 if no-upscale and image smaller)
        self.zoom_factor = 1.0     # >=1, additional zoom
        self.max_zoom_factor = 8.0

        # Viewport center in original image coords
        self.view_cx = 0.0
        self.view_cy = 0.0

        # Drag state
        self._drag_start = None  # (event.x, event.y, start_cx, start_cy)

        self.photo = None

        # Event bindings
        self.widget.bind('<MouseWheel>', self._on_mouse_wheel)
        self.widget.bind('<Button-4>', self._on_mouse_wheel)
        self.widget.bind('<Button-5>', self._on_mouse_wheel)
        self.widget.bind('<ButtonPress-1>', self._on_drag_start)
        self.widget.bind('<B1-Motion>', self._on_drag_move)
        self.widget.bind('<Double-Button-1>', self.reset_view)

    # ---------- Public API ----------

    def set_image(self, pil_image):
        if pil_image is None:
            return
        self.orig_image = pil_image
        self._recompute_base_scale()
        self.zoom_factor = 1.0
        iw, ih = self.orig_image.size
        # Start centered
        self.view_cx = iw / 2
        self.view_cy = ih / 2
        self._build_fit_image()
        self._refresh()

    def zoom_in(self, event=None):
        self._apply_zoom(1.25, center=None)

    def zoom_out(self, event=None):
        self._apply_zoom(1/1.25, center=None)

    def pan(self, dx_pixels: int, dy_pixels: int):
        if not self.orig_image or self.zoom_factor <= 1 and self.base_scale == 1:
            return
        vis_w, vis_h = self._visible_region_size()
        # Convert screen delta to original coords delta
        scale_total = self.base_scale * self.zoom_factor
        self.view_cx += dx_pixels / scale_total
        self.view_cy += dy_pixels / scale_total
        self._clamp_center(vis_w, vis_h)
        self._refresh()

    def reset_view(self, event=None):
        if not self.orig_image:
            return
        self._recompute_base_scale()
        self.zoom_factor = 1.0
        iw, ih = self.orig_image.size
        self.view_cx = iw / 2
        self.view_cy = ih / 2
        self._build_fit_image()
        self._refresh()

    # ---------- Internal computations ----------

    def _recompute_base_scale(self):
        iw, ih = self.orig_image.size
        sw, sh = self.screen_w, self.screen_h
        fit_scale = min(sw / iw, sh / ih)
        if not self.allow_upscale:
            fit_scale = min(1.0, fit_scale)
        self.base_scale = fit_scale

    def _build_fit_image(self):
        iw, ih = self.orig_image.size
        scaled_w = int(iw * self.base_scale)
        scaled_h = int(ih * self.base_scale)
        fit = self.orig_image if (scaled_w == iw and scaled_h == ih) else self.orig_image.resize((scaled_w, scaled_h), Image.LANCZOS)
        # Place centered on black background same as previous behavior
        base = Image.new('RGB', (self.screen_w, self.screen_h), 'black')
        x = (self.screen_w - scaled_w) // 2
        y = (self.screen_h - scaled_h) // 2
        base.paste(fit, (x, y))
        self.fit_image = base

    def _visible_region_size(self):
        """Return size of the visible screen area in original image coordinates."""
        scale_total = self.base_scale * self.zoom_factor
        return self.screen_w / scale_total, self.screen_h / scale_total

    def _clamp_center(self, vis_w, vis_h):
        iw, ih = self.orig_image.size
        half_w = vis_w / 2
        half_h = vis_h / 2
        if vis_w >= iw:
            self.view_cx = iw / 2
        else:
            if self.view_cx - half_w < 0:
                self.view_cx = half_w
            elif self.view_cx + half_w > iw:
                self.view_cx = iw - half_w
        if vis_h >= ih:
            self.view_cy = ih / 2
        else:
            if self.view_cy - half_h < 0:
                self.view_cy = half_h
            elif self.view_cy + half_h > ih:
                self.view_cy = ih - half_h

    def _apply_zoom(self, factor: float, center):
        if not self.orig_image:
            return
        old_zoom = self.zoom_factor
        new_zoom = max(1.0, min(self.max_zoom_factor, self.zoom_factor * factor))
        if new_zoom == old_zoom:
            return

        # Determine logical center point under cursor in original coords
        vis_w_old, vis_h_old = self._visible_region_size()
        if center is None:
            cx_screen = self.screen_w / 2
            cy_screen = self.screen_h / 2
        else:
            cx_screen, cy_screen = center
        # Map screen point to original coords before zoom
        left_old = self.view_cx - vis_w_old / 2
        top_old = self.view_cy - vis_h_old / 2
        orig_cx = left_old + (cx_screen / self.screen_w) * vis_w_old
        orig_cy = top_old + (cy_screen / self.screen_h) * vis_h_old

        # Apply new zoom
        self.zoom_factor = new_zoom
        vis_w_new, vis_h_new = self._visible_region_size()
        # Keep orig_cx/orig_cy under cursor -> solve new center
        left_new = orig_cx - (cx_screen / self.screen_w) * vis_w_new
        top_new = orig_cy - (cy_screen / self.screen_h) * vis_h_new
        self.view_cx = left_new + vis_w_new / 2
        self.view_cy = top_new + vis_h_new / 2
        self._clamp_center(vis_w_new, vis_h_new)
        self._refresh()

    def _refresh(self):
        if not self.orig_image:
            return
        if self.zoom_factor == 1.0:
            disp = self.fit_image
        else:
            vis_w, vis_h = self._visible_region_size()
            left = self.view_cx - vis_w / 2
            top = self.view_cy - vis_h / 2
            box = (int(left), int(top), int(left + vis_w), int(top + vis_h))
            crop = self.orig_image.crop(box)
            # Scale crop directly to screen size (fills; natural cropping)
            disp = crop.resize((self.screen_w, self.screen_h), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(disp)
        self.widget.config(image=self.photo)
        self.widget.image = self.photo
        if self.on_image_changed:
            self.on_image_changed()

    # ---------- Event handlers ----------

    def _on_mouse_wheel(self, event):
        delta = 0
        if event.num == 4:
            delta = 1
        elif event.num == 5:
            delta = -1
        elif hasattr(event, 'delta'):
            delta = 1 if event.delta > 0 else -1
        factor = 1.15 if delta > 0 else 1/1.15
        self._apply_zoom(factor, center=(event.x, event.y))

    def _on_drag_start(self, event):
        if not self.orig_image:
            return
        self._drag_start = (event.x, event.y, self.view_cx, self.view_cy)

    def _on_drag_move(self, event):
        if self._drag_start is None or not self.orig_image:
            return
        sx, sy, start_cx, start_cy = self._drag_start
        dx = sx - event.x
        dy = sy - event.y
        scale_total = self.base_scale * self.zoom_factor
        # Translate pixels to original coords
        self.view_cx = start_cx + dx / scale_total
        self.view_cy = start_cy + dy / scale_total
        vis_w, vis_h = self._visible_region_size()
        self._clamp_center(vis_w, vis_h)
        self._refresh()
