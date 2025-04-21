# -*- coding: utf-8 -*-
"""
Multi Crop App
A simple Windows application to select multiple rectangular regions (crops)
from an image and export them simultaneously.

Features:
- Load various image formats.
- Draw, move, resize multiple crop rectangles.
- Select crops via canvas click or listbox.
- Zoom and Pan the image view.
- Rename individual crops.
- Keyboard shortcuts for common actions (Open, Save, Save As, Delete, Nudge, Resize).
- Save: Creates a subfolder named after the image (next to it) and saves crops
  sequentially (imagename_1.jpg, ...). Remembers this location.
- Save As: Prompts for a folder and saves crops using their current names.
  Updates the default save location for subsequent "Save" clicks.
- Status bar showing coordinates, zoom level, selected crop size, and current action.
- Unsaved changes warning on close or new image load.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, Listbox
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import uuid
import math
import re # For parsing crop numbers and sanitizing filenames

# --- Constants ---
RECT_TAG_PREFIX = "crop_rect_"
DEFAULT_RECT_COLOR = "red"
SELECTED_RECT_COLOR = "blue"
RECT_WIDTH = 2
SELECTED_RECT_WIDTH = 3 # Make selected rectangle thicker
MIN_CROP_SIZE = 10 # Minimum width/height for a crop in image pixels
APP_NAME = "Multi Image Cropper"

# --- Main Application Class ---
class MultiCropApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title(APP_NAME)
        self.geometry("1100x750") # Initial size
        self.minsize(800, 600)    # Minimum window size
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        # --- State Variables ---
        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.tk_image = None
        self.canvas_image_id = None
        self.crops = {} # {crop_id: {'coords':(x1,y1,x2,y2), 'name': name, 'rect_id': id, 'order': int}}
        self.selected_crop_id = None
        self.next_crop_order_num = 1
        # --- Req: Save/Save As State ---
        self.current_save_dir = None # Stores the target dir for the current image session
        self.is_dirty = False # Track unsaved changes

        # Drawing/Editing State (Same as before)
        self.start_x, self.start_y = None, None
        self.current_rect_id = None
        self.is_drawing, self.is_moving, self.is_resizing = False, False, False
        self.resize_handle = None
        self.move_offset_x, self.move_offset_y = 0, 0
        self.start_coords_img = None

        # Zoom/Pan State (Same as before)
        self.zoom_factor = 1.0
        self.pan_start_x, self.pan_start_y = 0, 0
        self.is_panning = False
        self.canvas_offset_x, self.canvas_offset_y = 0, 0

        # --- UI Layout ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0) # Status bar

        # --- Main Content Frame ---
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.main_frame.grid_columnconfigure(0, weight=3) # Image area
        self.main_frame.grid_columnconfigure(1, weight=1) # Control panel
        self.main_frame.grid_rowconfigure(0, weight=1)

        # --- Left Frame (Image Display) ---
        self.image_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.image_frame.grid_rowconfigure(0, weight=1)
        self.image_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.image_frame, bg="gray90", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # --- Right Frame (Controls) ---
        self.control_frame = ctk.CTkFrame(self.main_frame, width=280)
        self.control_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False)
        # Configure columns for side-by-side buttons where needed
        self.control_frame.grid_columnconfigure(0, weight=1)
        self.control_frame.grid_columnconfigure(1, weight=1)
        # Configure row weights
        self.control_frame.grid_rowconfigure(4, weight=1) # Listbox row grows

        # Control Buttons
        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image (Ctrl+O)", command=self.handle_open)
        self.btn_select_image.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="ew")

        # --- Req: Save and Save As Buttons ---
        self.btn_save = ctk.CTkButton(self.control_frame, text="Save (Ctrl+S)", command=self.handle_save, state=tk.DISABLED)
        self.btn_save.grid(row=1, column=0, padx=(10, 5), pady=5, sticky="ew")

        self.btn_save_as = ctk.CTkButton(self.control_frame, text="Save As...", command=self.handle_save_as, state=tk.DISABLED)
        self.btn_save_as.grid(row=1, column=1, padx=(5, 10), pady=5, sticky="ew")
        # --- End Save/Save As Buttons ---

        # Crop List Area
        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List (Double-click to rename):")
        self.lbl_crop_list.grid(row=2, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="w")

        self.crop_listbox = Listbox(self.control_frame, bg='white', fg='black',
                                    selectbackground='#CDEAFE', selectforeground='black',
                                    highlightthickness=1, highlightbackground="#CCCCCC",
                                    highlightcolor="#89C4F4", borderwidth=0, exportselection=False)
        self.crop_listbox.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")
        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        self.crop_listbox.bind("<Double-Button-1>", self.prompt_rename_selected_crop_event)

        # Rename/Delete Buttons
        self.btn_rename_crop = ctk.CTkButton(self.control_frame, text="Rename", command=self.prompt_rename_selected_crop, state=tk.DISABLED)
        self.btn_rename_crop.grid(row=4, column=0, padx=(10, 5), pady=(5, 10), sticky="sew") # sticky includes south

        self.btn_delete_crop = ctk.CTkButton(self.control_frame, text="Delete (Del)", command=self.delete_selected_crop, state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F")
        self.btn_delete_crop.grid(row=4, column=1, padx=(5, 10), pady=(5, 10), sticky="sew") # sticky includes south

        # --- Status Bar ---
        self.status_bar = ctk.CTkFrame(self, height=25, fg_color="gray85")
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=0, pady=(0,0))
        self.status_bar.grid_columnconfigure(0, weight=1) # Coords
        self.status_bar.grid_columnconfigure(1, weight=1) # Action
        self.status_bar.grid_columnconfigure(2, weight=1) # Zoom/Select

        self.lbl_status_coords = ctk.CTkLabel(self.status_bar, text=" Img Coords: --- ", text_color="gray30", height=20, anchor="w")
        self.lbl_status_coords.grid(row=0, column=0, sticky="w", padx=(10, 0))
        self.lbl_status_action = ctk.CTkLabel(self.status_bar, text="Ready", text_color="gray30", height=20, anchor="center")
        self.lbl_status_action.grid(row=0, column=1, sticky="ew")
        self.lbl_status_zoom_select = ctk.CTkLabel(self.status_bar, text="Zoom: 100.0% | Sel: --- ", text_color="gray30", height=20, anchor="e")
        self.lbl_status_zoom_select.grid(row=0, column=2, sticky="e", padx=(0, 10))

        # --- Bindings ---
        # Canvas Mouse Bindings (Same as before)
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<ButtonPress-4>", lambda e: self.on_mouse_wheel(e, 1))
        self.canvas.bind("<ButtonPress-5>", lambda e: self.on_mouse_wheel(e, -1))
        self.canvas.bind("<ButtonPress-2>", self.on_pan_press)
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)
        self.canvas.bind("<Motion>", self.on_mouse_motion_canvas)
        self.canvas.bind("<Enter>", self.on_mouse_motion_canvas)
        self.canvas.bind("<Leave>", self.clear_status_coords)

        # Global Keyboard Bindings
        self.bind_all("<Control-o>", self.handle_open_event)
        self.bind_all("<Control-O>", self.handle_open_event)
        # --- Req: Ctrl+S triggers Save (not Save As) ---
        self.bind_all("<Control-s>", self.handle_save_event)
        self.bind_all("<Control-S>", self.handle_save_event)
        # Consider Ctrl+Shift+S for Save As? (Optional)
        # self.bind_all("<Control-Shift-KeyPress-S>", self.handle_save_as_event)
        self.bind_all("<Delete>", self.delete_selected_crop_event)
        # Nudge/Resize Bindings (Same as before)
        self.bind_all("<Left>", lambda e: self.handle_nudge(-1, 0))
        self.bind_all("<Right>", lambda e: self.handle_nudge(1, 0))
        self.bind_all("<Up>", lambda e: self.handle_nudge(0, -1))
        self.bind_all("<Down>", lambda e: self.handle_nudge(0, 1))
        self.bind_all("<Shift-Left>", lambda e: self.handle_resize_key(-1, 0, 'w'))
        self.bind_all("<Shift-Right>", lambda e: self.handle_resize_key(1, 0, 'e'))
        self.bind_all("<Shift-Up>", lambda e: self.handle_resize_key(0, -1, 'n'))
        self.bind_all("<Shift-Down>", lambda e: self.handle_resize_key(0, 1, 's'))

        # Window Events
        self.bind("<Configure>", self.on_window_resize)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Initial status bar update
        self.update_status_bar()

    # --- Unsaved Changes Handling (Same as before) ---
    def set_dirty(self, dirty_state=True):
        if self.is_dirty != dirty_state:
            self.is_dirty = dirty_state
            title = APP_NAME
            if self.is_dirty:
                title += " *"
            self.title(title)

    def check_unsaved_changes(self):
        if not self.is_dirty:
            return True
        response = messagebox.askyesnocancel("Unsaved Changes",
                                             "You have unsaved crops. Do you want to save them before proceeding?",
                                             icon=messagebox.WARNING, parent=self)
        if response is True: # Yes (Save)
            # --- Req: 'Yes' should trigger 'Save', not 'Save As' ---
            self.handle_save() # Try to save using default/current location
            return not self.is_dirty # Proceed if save was successful
        elif response is False: # No (Don't Save)
            return True
        else: # Cancel
            return False

    def on_closing(self):
        if self.check_unsaved_changes():
            self.destroy()

    # --- Status Bar Update (Same as before) ---
    def update_status_bar(self, action_text=None, coords_text=None, selection_text=None):
        current_action = self.lbl_status_action.cget("text")
        current_coords = self.lbl_status_coords.cget("text")
        current_zoom_select = self.lbl_status_zoom_select.cget("text")
        # Split carefully to avoid errors if format changes unexpectedly
        parts = current_zoom_select.split('|', 1)
        current_zoom = parts[0].strip() if len(parts) > 0 else "Zoom: ---"
        current_select_info = parts[1].strip() if len(parts) > 1 else "Sel: ---"

        new_action = action_text if action_text is not None else current_action
        new_coords = coords_text if coords_text is not None else current_coords
        new_select_info = selection_text if selection_text is not None else current_select_info
        new_zoom = f"Zoom: {self.zoom_factor:.1%}" # Always update zoom

        self.lbl_status_action.configure(text=new_action)
        self.lbl_status_coords.configure(text=new_coords)
        self.lbl_status_zoom_select.configure(text=f"{new_zoom} | {new_select_info}")

    def clear_status_coords(self, event=None):
        self.update_status_bar(coords_text=" Img Coords: --- ")

    def on_mouse_motion_canvas(self, event):
        coords_text = " Img Coords: --- "
        if self.original_image:
            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            img_x, img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
            if img_x is not None and img_y is not None:
                 img_w, img_h = self.original_image.size
                 clamped_x = max(0, min(img_x, img_w))
                 clamped_y = max(0, min(img_y, img_h))
                 coords_text = f" Img Coords: {int(clamped_x):>4}, {int(clamped_y):>4}"
        self.update_status_bar(coords_text=coords_text)
        self.update_cursor(event)

    def update_status_bar_selection(self):
        selection_text = " Sel: --- "
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            coords = self.crops[self.selected_crop_id].get('coords')
            if coords and len(coords) == 4:
                 w = coords[2] - coords[0]
                 h = coords[3] - coords[1]
                 selection_text = f" Sel: {max(0, int(w))}x{max(0, int(h))} px"
        self.update_status_bar(selection_text=selection_text)

    # --- Shortcut Handlers ---
    def handle_open_event(self, event=None):
        self.handle_open()
        return "break"

    def handle_open(self):
        self.select_image()

    # --- Req: Ctrl+S Handler ---
    def handle_save_event(self, event=None):
        self.handle_save() # Trigger the normal "Save" action
        return "break"

    # --- Req: "Save" Button Handler ---
    def handle_save(self):
        """Saves crops using the default naming convention to the last known/default directory."""
        if not self._check_save_preconditions(): return

        target_dir = self.current_save_dir

        # If no directory known for this session, calculate the default
        if not target_dir:
            try:
                img_dir = os.path.dirname(self.image_path)
                base_name = os.path.splitext(os.path.basename(self.image_path))[0]
                # Default folder is a subfolder named after the image, next to the image
                target_dir = os.path.join(img_dir, base_name)
                # Create the directory if it doesn't exist
                os.makedirs(target_dir, exist_ok=True)
                self.current_save_dir = target_dir # Remember this default dir for next Save
            except OSError as e:
                messagebox.showerror("Directory Error", f"Could not create default save directory:\n{target_dir}\n{e}", parent=self)
                self.update_status_bar(action_text="Save Failed (Dir Error)")
                return
            except Exception as e: # Catch other potential errors (e.g., invalid image_path)
                 messagebox.showerror("Error", f"Could not determine default save directory:\n{e}", parent=self)
                 self.update_status_bar(action_text="Save Failed (Dir Error)")
                 return

        # Perform the actual save using the determined directory and sequential naming
        self._perform_save(target_dir=target_dir, use_sequential_naming=True)

    # --- Req: "Save As" Button Handler ---
    def handle_save_as(self):
        """Prompts user for a directory and saves crops using their current names."""
        if not self._check_save_preconditions(): return

        # Suggest the current save directory or the default image-based one
        initial_dir = self.current_save_dir
        if not initial_dir and self.image_path:
            try:
                 img_dir = os.path.dirname(self.image_path)
                 base_name = os.path.splitext(os.path.basename(self.image_path))[0]
                 initial_dir = os.path.join(img_dir, base_name)
            except: pass # Ignore errors determining default initial dir

        output_dir = filedialog.askdirectory(
            parent=self,
            title="Select Folder to Save Cropped Images",
            initialdir=initial_dir
        )

        if not output_dir: # User cancelled
            self.update_status_bar(action_text="Save As Cancelled")
            return

        # User selected a directory, remember it for subsequent "Save" clicks
        self.current_save_dir = output_dir

        # Perform the actual save using the chosen directory and crop names
        self._perform_save(target_dir=output_dir, use_sequential_naming=False)

    def _check_save_preconditions(self):
        """Checks if image and crops exist before saving. Returns True if okay, False otherwise."""
        if not self.original_image or not self.image_path:
            messagebox.showwarning("Save Error", "Cannot save - No image loaded.", parent=self)
            return False
        if not self.crops:
            messagebox.showwarning("Save Error", "Cannot save - No crops defined.", parent=self)
            return False
        return True

    # --- Nudge/Resize Handlers (Same as before) ---
    def handle_nudge(self, dx_img, dy_img):
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            crop_id = self.selected_crop_id
            coords = self.crops[crop_id].get('coords')
            if not coords: return
            x1, y1, x2, y2 = coords
            new_x1, new_y1, new_x2, new_y2 = x1 + dx_img, y1 + dy_img, x2 + dx_img, y2 + dy_img
            if self.update_crop_coords(crop_id, (new_x1, new_y1, new_x2, new_y2)):
                self.redraw_all_crops()
                self.update_status_bar(action_text="Nudged Crop")
                self.update_status_bar_selection()

    def handle_resize_key(self, dx_img, dy_img, handle_direction):
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            crop_id = self.selected_crop_id
            coords = self.crops[crop_id].get('coords')
            if not coords: return
            x1, y1, x2, y2 = coords
            nx1, ny1, nx2, ny2 = x1, y1, x2, y2
            if 'n' in handle_direction: ny1 += dy_img
            if 's' in handle_direction: ny2 += dy_img
            if 'w' in handle_direction: nx1 += dx_img
            if 'e' in handle_direction: nx2 += dx_img
            if self.update_crop_coords(crop_id, (nx1, ny1, nx2, ny2)):
                self.redraw_all_crops()
                self.update_status_bar(action_text="Resized Crop")
                self.update_status_bar_selection()

    # --- Image Handling (Reset save dir on new image) ---
    def select_image(self):
        if not self.check_unsaved_changes(): return

        path = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp"), ("All Files", "*.*")]
        )
        if not path:
            self.update_status_bar(action_text="Image Selection Cancelled")
            return

        self.update_status_bar(action_text="Loading Image...")
        self.update_idletasks()

        try:
            new_image = Image.open(path)
            # Basic mode conversion for display/saving compatibility
            if new_image.mode == 'CMYK': new_image = new_image.convert('RGB')
            elif new_image.mode == 'P': new_image = new_image.convert('RGBA')

            self.image_path = path
            self.original_image = new_image

            # Calculate initial fit (Same logic as before)
            # ... (fit calculation logic) ...
            self.update_idletasks()
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            if canvas_width <= 1: canvas_width = self.canvas.winfo_reqwidth()
            if canvas_height <= 1: canvas_height = self.canvas.winfo_reqheight()
            img_width, img_height = self.original_image.size
            if img_width <= 0 or img_height <= 0: raise ValueError("Image has invalid dimensions")
            zoom_h = (canvas_width / img_width) if img_width > 0 else 1
            zoom_v = (canvas_height / img_height) if img_height > 0 else 1
            initial_zoom = min(zoom_h, zoom_v, 1.0)
            padding_factor = 0.98
            self.zoom_factor = initial_zoom * padding_factor
            display_w = img_width * self.zoom_factor
            display_h = img_height * self.zoom_factor
            self.canvas_offset_x = math.ceil((canvas_width - display_w) / 2)
            self.canvas_offset_y = math.ceil((canvas_height - display_h) / 2)
            # --- End Fit Calculation ---

            # Reset state for the new image
            self.clear_crops_and_list()
            self.next_crop_order_num = 1
            self.current_save_dir = None # <<< Reset known save directory for new image

            self.display_image_on_canvas()
            # Disable save buttons until crops exist
            self.btn_save.configure(state=tk.DISABLED)
            self.btn_save_as.configure(state=tk.DISABLED)
            self.set_dirty(False)
            self.update_status_bar(action_text="Image Loaded Successfully")

        except FileNotFoundError:
            messagebox.showerror("Error", f"Image file not found:\n{path}", parent=self)
            self.update_status_bar(action_text="Error: File Not Found")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open or process image:\n{e}", parent=self)
            # Reset relevant state on error
            self.image_path = None
            self.original_image = None
            self.clear_crops_and_list()
            self.canvas.delete("all")
            self.tk_image = None
            self.display_image = None
            self.btn_save.configure(state=tk.DISABLED)
            self.btn_save_as.configure(state=tk.DISABLED)
            self.set_dirty(False)
            self.current_save_dir = None
            self.update_status_bar(action_text="Error Loading Image")

    # --- display_image_on_canvas, clear_crops_and_list (Same as before) ---
    def display_image_on_canvas(self):
        if not self.original_image: self.canvas.delete("all"); return
        disp_w = max(1, int(self.original_image.width * self.zoom_factor))
        disp_h = max(1, int(self.original_image.height * self.zoom_factor))
        try:
            self.display_image = self.original_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
            self.tk_image = ImageTk.PhotoImage(self.display_image)
        except Exception as e:
            print(f"Error during image resize/PhotoImage creation: {e}")
            self.canvas.delete("all"); self.update_status_bar(action_text="Display Error"); return
        self.canvas.delete("all")
        int_offset_x = int(round(self.canvas_offset_x))
        int_offset_y = int(round(self.canvas_offset_y))
        self.canvas_image_id = self.canvas.create_image(int_offset_x, int_offset_y, anchor=tk.NW, image=self.tk_image, tags="image")
        self.redraw_all_crops()

    def clear_crops_and_list(self):
        self.canvas.delete("crop_rect")
        self.crops.clear()
        self.crop_listbox.delete(0, tk.END)
        self.selected_crop_id = None
        self.btn_delete_crop.configure(state=tk.DISABLED)
        self.btn_rename_crop.configure(state=tk.DISABLED)
        # Save buttons state depends on crops, handled elsewhere

    # --- Coordinate Conversion (Same as before) ---
    def canvas_to_image_coords(self, canvas_x, canvas_y):
        if not self.original_image or self.zoom_factor <= 0: return None, None
        img_x = (canvas_x - self.canvas_offset_x) / self.zoom_factor
        img_y = (canvas_y - self.canvas_offset_y) / self.zoom_factor
        return img_x, img_y

    def image_to_canvas_coords(self, img_x, img_y):
        if not self.original_image: return None, None
        canvas_x = (img_x * self.zoom_factor) + self.canvas_offset_x
        canvas_y = (img_y * self.zoom_factor) + self.canvas_offset_y
        return canvas_x, canvas_y

    # --- Crop Handling (add, select, update_coords, redraw, delete) ---
    # Add: Enable *both* save buttons when first crop added
    def add_crop(self, x1_img, y1_img, x2_img, y2_img):
        if not self.original_image: return
        img_w, img_h = self.original_image.size
        x1_img, y1_img = max(0, min(x1_img, img_w)), max(0, min(y1_img, img_h))
        x2_img, y2_img = max(0, min(x2_img, img_w)), max(0, min(y2_img, img_h))
        coords = (min(x1_img, x2_img), min(y1_img, y2_img), max(x1_img, x2_img), max(y1_img, y2_img))
        if (coords[2] - coords[0]) < MIN_CROP_SIZE or (coords[3] - coords[1]) < MIN_CROP_SIZE:
            if self.current_rect_id and self.current_rect_id in self.canvas.find_withtag("temp_rect"): self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None; self.update_status_bar(action_text="Crop Too Small"); return
        crop_id = str(uuid.uuid4())
        crop_name = f"Crop_{self.next_crop_order_num}"
        current_order_num = self.next_crop_order_num; self.next_crop_order_num += 1
        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])
        if cx1 is None: print("Error: Coordinate conversion failed."); self.update_status_bar(action_text="Error Adding Crop"); return
        rect_id = self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=SELECTED_RECT_COLOR, width=SELECTED_RECT_WIDTH, tags=(RECT_TAG_PREFIX + crop_id, "crop_rect"))
        self.crops[crop_id] = {'coords': coords, 'name': crop_name, 'rect_id': rect_id, 'order': current_order_num}
        self.crop_listbox.insert(tk.END, crop_name)
        self.crop_listbox.selection_clear(0, tk.END); self.crop_listbox.selection_set(tk.END); self.crop_listbox.activate(tk.END); self.crop_listbox.see(tk.END)
        self.select_crop(crop_id, from_listbox=False)
        # Enable Save buttons
        self.btn_save.configure(state=tk.NORMAL)
        self.btn_save_as.configure(state=tk.NORMAL)
        self.set_dirty()
        self.update_status_bar(action_text="Crop Added")

    # Select: Same as before
    def select_crop(self, crop_id, from_listbox=True):
        if self.selected_crop_id == crop_id and crop_id is not None: self.update_status_bar_selection(); return
        # Deselect previous
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            prev_data = self.crops[self.selected_crop_id]; prev_rect_id = prev_data.get('rect_id')
            if prev_rect_id and prev_rect_id in self.canvas.find_withtag(prev_rect_id): self.canvas.itemconfig(prev_rect_id, outline=DEFAULT_RECT_COLOR, width=RECT_WIDTH)
        self.selected_crop_id = crop_id
        # Select new
        if crop_id and crop_id in self.crops:
            data = self.crops[crop_id]; rect_id = data.get('rect_id')
            if rect_id and rect_id in self.canvas.find_withtag(rect_id):
                 self.canvas.itemconfig(rect_id, outline=SELECTED_RECT_COLOR, width=SELECTED_RECT_WIDTH); self.canvas.tag_raise(rect_id)
                 self.btn_delete_crop.configure(state=tk.NORMAL); self.btn_rename_crop.configure(state=tk.NORMAL)
                 if not from_listbox:
                     index = -1
                     for i in range(self.crop_listbox.size()):
                         if self.crop_listbox.get(i) == data.get('name'): index = i; break
                     if index != -1: self.crop_listbox.selection_clear(0, tk.END); self.crop_listbox.selection_set(index); self.crop_listbox.activate(index); self.crop_listbox.see(index)
            else: self.selected_crop_id = None; self.btn_delete_crop.configure(state=tk.DISABLED); self.btn_rename_crop.configure(state=tk.DISABLED)
        else: # Deselection
            self.selected_crop_id = None
            if not from_listbox: self.crop_listbox.selection_clear(0, tk.END)
            self.btn_delete_crop.configure(state=tk.DISABLED); self.btn_rename_crop.configure(state=tk.DISABLED)
        self.update_status_bar_selection()

    # Update Coords: Same as before (sets dirty flag)
    def update_crop_coords(self, crop_id, new_img_coords):
        if crop_id in self.crops and self.original_image:
            img_w, img_h = self.original_image.size
            x1, y1, x2, y2 = new_img_coords
            x1, y1 = max(0, min(x1, img_w)), max(0, min(y1, img_h))
            x2, y2 = max(0, min(x2, img_w)), max(0, min(y2, img_h))
            final_x1, final_y1 = min(x1, x2), min(y1, y2)
            final_x2, final_y2 = max(x1, x2), max(y1, y2)
            if (final_x2 - final_x1) < MIN_CROP_SIZE or (final_y2 - final_y1) < MIN_CROP_SIZE: return False
            new_coords_tuple = (final_x1, final_y1, final_x2, final_y2)
            if self.crops[crop_id]['coords'] != new_coords_tuple:
                 self.crops[crop_id]['coords'] = new_coords_tuple; self.set_dirty(); return True
            else: return True # Valid but unchanged
        return False

    # Redraw: Same as before
    def redraw_all_crops(self):
        all_canvas_items = self.canvas.find_all()
        for crop_id, data in self.crops.items():
            coords = data.get('coords'); rect_id = data.get('rect_id')
            if not coords or len(coords) != 4: continue
            img_x1, img_y1, img_x2, img_y2 = coords
            cx1, cy1 = self.image_to_canvas_coords(img_x1, img_y1)
            cx2, cy2 = self.image_to_canvas_coords(img_x2, img_y2)
            if cx1 is None: continue
            is_selected = (crop_id == self.selected_crop_id)
            color = SELECTED_RECT_COLOR if is_selected else DEFAULT_RECT_COLOR
            width = SELECTED_RECT_WIDTH if is_selected else RECT_WIDTH
            tags_tuple = (RECT_TAG_PREFIX + crop_id, "crop_rect")
            if rect_id and rect_id in all_canvas_items:
                 self.canvas.coords(rect_id, cx1, cy1, cx2, cy2); self.canvas.itemconfig(rect_id, outline=color, width=width, tags=tags_tuple)
            else:
                 new_rect_id = self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=color, width=width, tags=tags_tuple)
                 self.crops[crop_id]['rect_id'] = new_rect_id
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            selected_rect_id = self.crops[self.selected_crop_id].get('rect_id')
            if selected_rect_id and selected_rect_id in self.canvas.find_all(): self.canvas.tag_raise(selected_rect_id)
        self.update_status_bar_selection()

    # Delete: Disable *both* save buttons if no crops left
    def delete_selected_crop(self):
        if not self.selected_crop_id or self.selected_crop_id not in self.crops: return
        crop_id_to_delete = self.selected_crop_id; data = self.crops[crop_id_to_delete]
        rect_id = data.get('rect_id'); current_name = data.get('name')
        if rect_id and rect_id in self.canvas.find_all(): self.canvas.delete(rect_id)
        index_to_delete = -1
        if current_name:
             for i in range(self.crop_listbox.size()):
                 if self.crop_listbox.get(i) == current_name: index_to_delete = i; break
        del self.crops[crop_id_to_delete]
        if index_to_delete != -1: self.crop_listbox.delete(index_to_delete)
        self.selected_crop_id = None
        self.btn_delete_crop.configure(state=tk.DISABLED); self.btn_rename_crop.configure(state=tk.DISABLED)
        if not self.crops:
             self.btn_save.configure(state=tk.DISABLED) # <<< Disable Save
             self.btn_save_as.configure(state=tk.DISABLED) # <<< Disable Save As
        self.set_dirty()
        self.update_status_bar(action_text="Crop Deleted")
        if self.crop_listbox.size() > 0:
            new_index = max(0, index_to_delete - 1)
            if index_to_delete == 0 or index_to_delete == -1: new_index = 0
            if new_index >= self.crop_listbox.size(): new_index = self.crop_listbox.size() - 1
            self.crop_listbox.selection_set(new_index); self.on_listbox_select()
        else: self.crop_listbox.selection_clear(0, tk.END); self.select_crop(None, from_listbox=False)

    # Rename: Same as before
    def prompt_rename_selected_crop_event(self, event=None): self.prompt_rename_selected_crop()
    def prompt_rename_selected_crop(self):
        if not self.selected_crop_id or self.selected_crop_id not in self.crops: messagebox.showwarning("Rename Error", "Please select a crop...", parent=self); return
        crop_id = self.selected_crop_id; current_name = self.crops[crop_id].get('name', '')
        dialog = ctk.CTkInputDialog(text=f"Enter new name for '{current_name}':", title="Rename Crop", entry_fg_color="white", entry_text_color="black")
        dialog.geometry(f"+{self.winfo_x()+200}+{self.winfo_y()+200}")
        new_name_raw = dialog.get_input()
        if new_name_raw is None or not new_name_raw.strip(): self.update_status_bar(action_text="Rename Cancelled"); return
        new_name = new_name_raw.strip()
        for c_id, data in self.crops.items():
            if c_id != crop_id and data.get('name') == new_name: messagebox.showerror("Rename Error", f"Name '{new_name}' already exists.", parent=self); return
        self.crops[crop_id]['name'] = new_name
        index = -1
        for i in range(self.crop_listbox.size()):
            if self.crop_listbox.get(i) == current_name: index = i; break
        if index != -1: self.crop_listbox.delete(index); self.crop_listbox.insert(index, new_name); self.crop_listbox.selection_set(index); self.crop_listbox.activate(index)
        self.set_dirty(); self.update_status_bar(action_text="Crop Renamed")

    # --- Mouse Events (on_press, drag, release - same as before) ---
    def on_mouse_press(self, event):
        self.canvas.focus_set(); canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        action_text = "Ready"
        handle = self.get_resize_handle(canvas_x, canvas_y)
        if handle and self.selected_crop_id:
            self.is_resizing = True; self.resize_handle = handle; self.start_x, self.start_y = canvas_x, canvas_y
            self.start_coords_img = self.crops[self.selected_crop_id].get('coords'); action_text = "Resizing Crop..."; self.update_status_bar(action_text=action_text); return
        overlapping_items = self.canvas.find_overlapping(canvas_x-1, canvas_y-1, canvas_x+1, canvas_y+1)
        clicked_crop_id = None
        for item_id in reversed(overlapping_items):
            tags = self.canvas.gettags(item_id)
            if tags and tags[0].startswith(RECT_TAG_PREFIX) and "crop_rect" in tags:
                crop_id = tags[0][len(RECT_TAG_PREFIX):];
                if crop_id in self.crops: clicked_crop_id = crop_id; break
        if clicked_crop_id:
            self.select_crop(clicked_crop_id); self.is_moving = True
            rect_coords = self.canvas.coords(self.crops[clicked_crop_id]['rect_id'])
            self.move_offset_x, self.move_offset_y = canvas_x - rect_coords[0], canvas_y - rect_coords[1]
            self.start_coords_img = self.crops[clicked_crop_id].get('coords'); action_text = "Moving Crop..."; self.update_status_bar(action_text=action_text); return
        if self.original_image:
            self.is_drawing = True; self.start_x, self.start_y = canvas_x, canvas_y
            self.current_rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline=SELECTED_RECT_COLOR, width=RECT_WIDTH, dash=(4, 4), tags=("temp_rect",))
            self.select_crop(None); action_text = "Drawing Crop..."; self.update_status_bar(action_text=action_text)

    def on_mouse_drag(self, event):
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        if self.is_drawing and self.current_rect_id:
            self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, canvas_x, canvas_y)
        elif self.is_moving and self.selected_crop_id:
            crop_id = self.selected_crop_id; rect_id = self.crops[crop_id]['rect_id']
            new_cx1 = canvas_x - self.move_offset_x; new_cy1 = canvas_y - self.move_offset_y
            current_canvas_coords = self.canvas.coords(rect_id); w = current_canvas_coords[2] - current_canvas_coords[0]; h = current_canvas_coords[3] - current_canvas_coords[1]
            new_cx2, new_cy2 = new_cx1 + w, new_cy1 + h
            img_x1, img_y1 = self.canvas_to_image_coords(new_cx1, new_cy1); img_x2, img_y2 = self.canvas_to_image_coords(new_cx2, new_cy2)
            if img_x1 is not None and self.update_crop_coords(crop_id, (img_x1, img_y1, img_x2, img_y2)): self.redraw_all_crops(); self.update_status_bar_selection()
        elif self.is_resizing and self.selected_crop_id and self.resize_handle and self.start_coords_img:
            crop_id = self.selected_crop_id; ox1_img, oy1_img, ox2_img, oy2_img = self.start_coords_img
            curr_img_x, curr_img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
            start_img_x_conv, start_img_y_conv = self.canvas_to_image_coords(self.start_x, self.start_y)
            if curr_img_x is None or start_img_x_conv is None: return
            dx_img, dy_img = curr_img_x - start_img_x_conv, curr_img_y - start_img_y_conv
            nx1, ny1, nx2, ny2 = ox1_img, oy1_img, ox2_img, oy2_img
            if 'n' in self.resize_handle: ny1 += dy_img;
            if 's' in self.resize_handle: ny2 += dy_img;
            if 'w' in self.resize_handle: nx1 += dx_img;
            if 'e' in self.resize_handle: nx2 += dx_img;
            if self.update_crop_coords(crop_id, (nx1, ny1, nx2, ny2)): self.redraw_all_crops(); self.update_status_bar_selection()

    def on_mouse_release(self, event):
        if self.is_drawing and self.current_rect_id:
            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            if self.current_rect_id in self.canvas.find_withtag("temp_rect"): self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            img_x1, img_y1 = self.canvas_to_image_coords(self.start_x, self.start_y); img_x2, img_y2 = self.canvas_to_image_coords(canvas_x, canvas_y)
            if img_x1 is not None and img_y1 is not None and img_x2 is not None and img_y2 is not None: self.add_crop(img_x1, img_y1, img_x2, img_y2)
            else: print("Failed to add crop due to coordinate conversion error."); self.update_status_bar(action_text="Error Adding Crop")
        self.is_drawing, self.is_moving, self.is_resizing = False, False, False
        self.resize_handle = None; self.start_x, self.start_y = None, None; self.start_coords_img = None
        self.update_cursor(event)
        if not (self.is_drawing and self.current_rect_id is None): self.update_status_bar(action_text="Ready")


    # --- Zoom/Pan (Same as before) ---
    def on_mouse_wheel(self, event, direction=None):
        if not self.original_image: return
        delta = 0
        if direction: delta = direction
        elif event.num == 5 or event.delta < 0: delta = -1
        elif event.num == 4 or event.delta > 0: delta = 1
        else: return
        zoom_increment, min_zoom, max_zoom = 1.1, 0.01, 25.0
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        img_x_before, img_y_before = self.canvas_to_image_coords(canvas_x, canvas_y)
        if img_x_before is None: return
        new_zoom = self.zoom_factor * zoom_increment if delta > 0 else self.zoom_factor / zoom_increment
        new_zoom = max(min_zoom, min(max_zoom, new_zoom))
        if abs(new_zoom - self.zoom_factor) < 0.0001: return
        self.zoom_factor = new_zoom
        self.canvas_offset_x = canvas_x - (img_x_before * self.zoom_factor)
        self.canvas_offset_y = canvas_y - (img_y_before * self.zoom_factor)
        self.display_image_on_canvas()
        self.update_status_bar(action_text=f"Zoom {('In' if delta > 0 else 'Out')}")

    def on_pan_press(self, event):
        if not self.original_image: return
        self.is_panning = True; self.pan_start_x, self.pan_start_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.canvas.config(cursor="fleur"); self.update_status_bar(action_text="Panning...")

    def on_pan_drag(self, event):
        if not self.is_panning or not self.original_image: return
        current_x, current_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        dx, dy = current_x - self.pan_start_x, current_y - self.pan_start_y
        self.canvas_offset_x += dx; self.canvas_offset_y += dy
        self.canvas.move("all", dx, dy)
        self.pan_start_x, self.pan_start_y = current_x, current_y

    def on_pan_release(self, event):
        self.is_panning = False; self.update_cursor(event); self.update_status_bar(action_text="Ready")

    # --- Listbox Selection (Same as before) ---
    def on_listbox_select(self, event=None):
        selection = self.crop_listbox.curselection()
        selected_id = None
        if selection:
            selected_index = selection[0]; selected_name = self.crop_listbox.get(selected_index)
            for crop_id, data in self.crops.items():
                if data.get('name') == selected_name: selected_id = crop_id; break
        self.select_crop(selected_id, from_listbox=True)

    # --- Resizing Helpers & Cursor (Same as before) ---
    def get_resize_handle(self, canvas_x, canvas_y):
        if not self.selected_crop_id or self.selected_crop_id not in self.crops: return None
        rect_id = self.crops[self.selected_crop_id].get('rect_id')
        if not rect_id or rect_id not in self.canvas.find_all(): return None
        cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id); handle_margin = 8
        if abs(canvas_x - cx1) < handle_margin and abs(canvas_y - cy1) < handle_margin: return 'nw'
        if abs(canvas_x - cx2) < handle_margin and abs(canvas_y - cy1) < handle_margin: return 'ne'
        if abs(canvas_x - cx1) < handle_margin and abs(canvas_y - cy2) < handle_margin: return 'sw'
        if abs(canvas_x - cx2) < handle_margin and abs(canvas_y - cy2) < handle_margin: return 'se'
        inner_buffer = handle_margin / 2
        if abs(canvas_y - cy1) < handle_margin and (cx1 + inner_buffer) < canvas_x < (cx2 - inner_buffer): return 'n'
        if abs(canvas_y - cy2) < handle_margin and (cx1 + inner_buffer) < canvas_x < (cx2 - inner_buffer): return 's'
        if abs(canvas_x - cx1) < handle_margin and (cy1 + inner_buffer) < canvas_y < (cy2 - inner_buffer): return 'w'
        if abs(canvas_x - cx2) < handle_margin and (cy1 + inner_buffer) < canvas_y < (cy2 - inner_buffer): return 'e'
        return None

    def update_cursor(self, event=None):
        new_cursor = ""
        if self.is_panning or self.is_moving: new_cursor = "fleur"
        elif self.is_resizing:
            handle = self.resize_handle
            if handle in ('nw', 'se'): new_cursor = "size_nw_se"
            elif handle in ('ne', 'sw'): new_cursor = "size_ne_sw"
            elif handle in ('n', 's'): new_cursor = "size_ns"
            elif handle in ('e', 'w'): new_cursor = "size_we"
        elif self.is_drawing: new_cursor = "crosshair"
        else: # Hover state
            if event:
                canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
                handle = self.get_resize_handle(canvas_x, canvas_y)
                if handle:
                    if handle in ('nw', 'se'): new_cursor = "size_nw_se"
                    elif handle in ('ne', 'sw'): new_cursor = "size_ne_sw"
                    elif handle in ('n', 's'): new_cursor = "size_ns"
                    elif handle in ('e', 'w'): new_cursor = "size_we"
                else: # Check for hover inside selected rect
                    if self.selected_crop_id and self.selected_crop_id in self.crops:
                        rect_id = self.crops[self.selected_crop_id].get('rect_id')
                        if rect_id and rect_id in self.canvas.find_all():
                            cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id); margin = 1
                            if (cx1 + margin) < canvas_x < (cx2 - margin) and (cy1 + margin) < canvas_y < (cy2 - margin): new_cursor = "fleur"
        if self.canvas.cget("cursor") != new_cursor: self.canvas.config(cursor=new_cursor)

    # --- Window Resize Handling (Same as before) ---
    def on_window_resize(self, event=None): pass

    # --- Req: Core Saving Logic ---
    def _perform_save(self, target_dir, use_sequential_naming):
        """Internal helper function to perform the actual saving process."""
        if not self.original_image or not self.image_path:
             print("Save Error: No image loaded.") # Should be caught earlier
             return

        self.update_status_bar(action_text="Saving...")
        self.update_idletasks()

        saved_count = 0
        error_count = 0
        error_messages = []

        # Sort crops by creation order
        def get_crop_order(item_tuple):
            return item_tuple[1].get('order', float('inf'))
        sorted_crop_items = sorted(self.crops.items(), key=get_crop_order)

        # Get base name for sequential naming if needed
        base_name = ""
        if use_sequential_naming:
             base_name = os.path.splitext(os.path.basename(self.image_path))[0]

        for i, (crop_id, data) in enumerate(sorted_crop_items):
            coords = data.get('coords')
            crop_name = data.get('name', f'Unnamed_Crop_{i+1}') # Use current name for Save As, fallback
            if not coords:
                error_count += 1; error_messages.append(f"Skipping '{crop_name}': Invalid data."); continue

            # Determine filename based on mode
            if use_sequential_naming:
                filename = f"{base_name}_{i+1}.jpg" # imagename_1.jpg, imagename_2.jpg ...
            else: # Use crop name for Save As
                safe_crop_name = re.sub(r'[\\/*?:"<>|]', '_', crop_name).rstrip('. ')
                if not safe_crop_name: safe_crop_name = f"Crop_{data.get('order', i+1)}"
                filename = f"{safe_crop_name}.jpg"

            filepath = os.path.join(target_dir, filename)
            int_coords = tuple(map(int, coords))

            try:
                cropped_img = self.original_image.crop(int_coords)
                # Handle transparency for JPG saving
                if cropped_img.mode in ('RGBA', 'P', 'LA'):
                    bg = Image.new("RGB", cropped_img.size, (255, 255, 255))
                    bg.paste(cropped_img, mask=cropped_img.split()[-1] if 'A' in cropped_img.mode else None)
                    cropped_img = bg
                elif cropped_img.mode != 'RGB':
                    cropped_img = cropped_img.convert('RGB')

                cropped_img.save(filepath, "JPEG", quality=95, optimize=True)
                saved_count += 1
            except Exception as e:
                error_count += 1; err_msg = f"Error saving '{filename}': {e}"; print(err_msg); error_messages.append(err_msg)

        # Final status update and message box
        if error_count == 0:
            self.set_dirty(False) # Clear unsaved changes flag on complete success
            messagebox.showinfo("Success", f"Successfully saved {saved_count} crops to:\n{target_dir}", parent=self)
            self.update_status_bar(action_text="Crops Saved Successfully")
        else:
            error_summary = "\n - ".join(error_messages[:3]);
            if len(error_messages) > 3: error_summary += "\n   (...more errors in console)"
            messagebox.showwarning("Partial Success", f"Saved {saved_count} crops to:\n{target_dir}\n\nFailed {error_count}:\n - {error_summary}", parent=self)
            self.update_status_bar(action_text="Save Complete (with errors)")

# --- Run the Application ---
if __name__ == "__main__":
    try: from ctypes import windll; windll.shcore.SetProcessDpiAwareness(1)
    except: pass # Ignore DPI awareness errors

    app = MultiCropApp()
    app.mainloop()
