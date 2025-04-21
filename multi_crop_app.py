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
- Keyboard shortcuts for common actions (Open, Save, Delete, Nudge, Resize).
- Choose output directory for saving crops.
- Crops saved sequentially based on creation order, using their current names.
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
        self.original_image = None # Stores the original PIL Image
        self.display_image = None  # Stores the potentially resized PIL Image for display
        self.tk_image = None       # Stores the PhotoImage for the canvas
        self.canvas_image_id = None # ID of the image item on the canvas
        # Enhanced crops dictionary: store original order number for reliable sorting
        self.crops = {} # {crop_id: {'coords':(x1,y1,x2,y2), 'name': name, 'rect_id': id, 'order': int}}
        self.selected_crop_id = None
        self.next_crop_order_num = 1 # Use this for reliable sorting/default naming
        self.last_saved_to_dir = None # Remember last save directory
        self.is_dirty = False # Track unsaved changes

        # Drawing/Editing State
        self.start_x, self.start_y = None, None
        self.current_rect_id = None # ID of the rectangle being drawn temporarily
        self.is_drawing, self.is_moving, self.is_resizing = False, False, False
        self.resize_handle = None # 'nw', 'ne', 'sw', 'se', 'n', 's', 'e', 'w'
        self.move_offset_x, self.move_offset_y = 0, 0
        self.start_coords_img = None # Stores image coords at start of move/resize

        # Zoom/Pan State
        self.zoom_factor = 1.0
        self.pan_start_x, self.pan_start_y = 0, 0
        self.is_panning = False
        self.canvas_offset_x, self.canvas_offset_y = 0, 0 # Top-left corner of image relative to canvas (0,0)

        # --- UI Layout ---
        self.grid_columnconfigure(0, weight=1) # Main area takes all horizontal space
        self.grid_rowconfigure(0, weight=1)    # Canvas/Controls row takes most vertical space
        self.grid_rowconfigure(1, weight=0)    # Status bar row has fixed height

        # --- Main Content Frame (Canvas + Controls) ---
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.main_frame.grid_columnconfigure(0, weight=3) # Image area gets more horizontal space
        self.main_frame.grid_columnconfigure(1, weight=1) # Control panel gets less
        self.main_frame.grid_rowconfigure(0, weight=1)    # Row containing canvas/controls fills vertical space

        # --- Left Frame (Image Display) ---
        self.image_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.image_frame.grid_rowconfigure(0, weight=1)
        self.image_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.image_frame, bg="gray90", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # --- Right Frame (Controls) ---
        self.control_frame = ctk.CTkFrame(self.main_frame, width=280) # Fixed width for controls
        self.control_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False) # Prevent frame resizing based on content
        self.control_frame.grid_columnconfigure(0, weight=1) # Allow buttons to expand horizontally
        self.control_frame.grid_columnconfigure(1, weight=1) # For rename/delete buttons side-by-side
        self.control_frame.grid_rowconfigure(3, weight=1) # Listbox takes available vertical space

        # Buttons
        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image (Ctrl+O)", command=self.handle_open)
        self.btn_select_image.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="ew")

        self.btn_save_crops = ctk.CTkButton(self.control_frame, text="Save All Crops (Ctrl+S)", command=self.handle_save, state=tk.DISABLED)
        self.btn_save_crops.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

        # Crop List Area
        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List (Double-click to rename):")
        self.lbl_crop_list.grid(row=2, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="w")

        self.crop_listbox = Listbox(self.control_frame, bg='white', fg='black',
                                    selectbackground='#CDEAFE', selectforeground='black',
                                    highlightthickness=1, highlightbackground="#CCCCCC", # Light border
                                    highlightcolor="#89C4F4", # Focus highlight color
                                    borderwidth=0, exportselection=False)
        self.crop_listbox.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")
        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        self.crop_listbox.bind("<Double-Button-1>", self.prompt_rename_selected_crop_event)

        # Rename/Delete Buttons
        self.btn_rename_crop = ctk.CTkButton(self.control_frame, text="Rename", command=self.prompt_rename_selected_crop, state=tk.DISABLED)
        self.btn_rename_crop.grid(row=4, column=0, padx=(10, 5), pady=(5, 10), sticky="ew")

        self.btn_delete_crop = ctk.CTkButton(self.control_frame, text="Delete (Del)", command=self.delete_selected_crop, state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F") # Red delete button
        self.btn_delete_crop.grid(row=4, column=1, padx=(5, 10), pady=(5, 10), sticky="ew")

        # --- Status Bar ---
        self.status_bar = ctk.CTkFrame(self, height=25, fg_color="gray85") # Slightly different color from canvas
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=0, pady=(0,0))
        # Configure columns to distribute space: Coords(left), Action(center), Zoom/Select(right)
        self.status_bar.grid_columnconfigure(0, weight=1) # Left aligned info
        self.status_bar.grid_columnconfigure(1, weight=1) # Center aligned info
        self.status_bar.grid_columnconfigure(2, weight=1) # Right aligned info

        self.lbl_status_coords = ctk.CTkLabel(self.status_bar, text=" Img Coords: --- ", text_color="gray30", height=20, anchor="w")
        self.lbl_status_coords.grid(row=0, column=0, sticky="w", padx=(10, 0))

        self.lbl_status_action = ctk.CTkLabel(self.status_bar, text="Ready", text_color="gray30", height=20, anchor="center")
        self.lbl_status_action.grid(row=0, column=1, sticky="ew")

        self.lbl_status_zoom_select = ctk.CTkLabel(self.status_bar, text="Zoom: 100.0% | Sel: --- ", text_color="gray30", height=20, anchor="e")
        self.lbl_status_zoom_select.grid(row=0, column=2, sticky="e", padx=(0, 10))

        # --- Bindings ---
        # Canvas Mouse Bindings
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)    # Left click press
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)         # Left click drag
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release) # Left click release
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)       # Mouse wheel scroll (Win/macOS)
        self.canvas.bind("<ButtonPress-4>", lambda e: self.on_mouse_wheel(e, 1)) # Scroll up (Linux)
        self.canvas.bind("<ButtonPress-5>", lambda e: self.on_mouse_wheel(e, -1)) # Scroll down (Linux)
        self.canvas.bind("<ButtonPress-2>", self.on_pan_press)      # Middle click press (or Alt+LeftClick depending on system)
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)           # Middle click drag
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)  # Middle click release
        self.canvas.bind("<Motion>", self.on_mouse_motion_canvas)   # Mouse movement over canvas
        self.canvas.bind("<Enter>", self.on_mouse_motion_canvas)    # Mouse enters canvas area
        self.canvas.bind("<Leave>", self.clear_status_coords)       # Mouse leaves canvas area

        # Global Keyboard Bindings
        self.bind_all("<Control-o>", self.handle_open_event) # Use bind_all for global shortcuts
        self.bind_all("<Control-O>", self.handle_open_event)
        self.bind_all("<Control-s>", self.handle_save_event)
        self.bind_all("<Control-S>", self.handle_save_event)
        self.bind_all("<Delete>", self.delete_selected_crop_event)
        # Nudge shortcuts (apply when canvas or listbox has focus potentially)
        self.bind_all("<Left>", lambda e: self.handle_nudge(-1, 0))
        self.bind_all("<Right>", lambda e: self.handle_nudge(1, 0))
        self.bind_all("<Up>", lambda e: self.handle_nudge(0, -1))
        self.bind_all("<Down>", lambda e: self.handle_nudge(0, 1))
        # Resize shortcuts (Shift + Arrows)
        self.bind_all("<Shift-Left>", lambda e: self.handle_resize_key(-1, 0, 'w'))
        self.bind_all("<Shift-Right>", lambda e: self.handle_resize_key(1, 0, 'e'))
        self.bind_all("<Shift-Up>", lambda e: self.handle_resize_key(0, -1, 'n'))
        self.bind_all("<Shift-Down>", lambda e: self.handle_resize_key(0, 1, 's'))

        # Window Events
        self.bind("<Configure>", self.on_window_resize) # Window resize event
        self.protocol("WM_DELETE_WINDOW", self.on_closing) # Window close button click

        # Initial status bar update
        self.update_status_bar()

    # --- Unsaved Changes Handling ---
    def set_dirty(self, dirty_state=True):
        """Marks the state as having unsaved changes and updates window title."""
        if self.is_dirty != dirty_state:
            self.is_dirty = dirty_state
            title = APP_NAME
            if self.is_dirty:
                title += " *" # Add asterisk to indicate unsaved changes
            self.title(title)

    def check_unsaved_changes(self):
        """
        Checks for unsaved changes and prompts user via messagebox.
        Returns:
            bool: True if it's okay to proceed (saved, chose not to save, or no changes),
                  False if the action should be cancelled.
        """
        if not self.is_dirty:
            return True

        response = messagebox.askyesnocancel("Unsaved Changes",
                                             "You have unsaved crops. Do you want to save them before proceeding?",
                                             icon=messagebox.WARNING)
        if response is True: # Yes (Save)
            self.handle_save()
            # Proceed only if save was successful (or user implicitly cancelled save dialog but still wants to proceed)
            # Check is_dirty again; if save was successful, it should be False.
            return not self.is_dirty
        elif response is False: # No (Don't Save)
            return True # User chose not to save, okay to proceed
        else: # Cancel
            return False # User cancelled the current action (e.g., loading new image, closing)

    def on_closing(self):
        """Handles the event when the user tries to close the window."""
        if self.check_unsaved_changes():
            self.destroy() # Close the application

    # --- Status Bar Update ---
    def update_status_bar(self, action_text=None, coords_text=None, selection_text=None):
        """Updates parts or all of the status bar. Uses current value if argument is None."""
        current_action = self.lbl_status_action.cget("text")
        current_coords = self.lbl_status_coords.cget("text")
        current_zoom_select = self.lbl_status_zoom_select.cget("text")
        current_zoom = current_zoom_select.split('|')[0].strip()
        current_select_info = current_zoom_select.split('|')[1].strip()

        new_action = action_text if action_text is not None else current_action
        new_coords = coords_text if coords_text is not None else current_coords
        new_select_info = selection_text if selection_text is not None else current_select_info
        new_zoom = f"Zoom: {self.zoom_factor:.1%}" # Always update zoom based on current factor

        self.lbl_status_action.configure(text=new_action)
        self.lbl_status_coords.configure(text=new_coords)
        self.lbl_status_zoom_select.configure(text=f"{new_zoom} | {new_select_info}")

    def clear_status_coords(self, event=None):
        """Clears the coordinate display part of the status bar."""
        self.update_status_bar(coords_text=" Img Coords: --- ")

    def on_mouse_motion_canvas(self, event):
        """Update coordinates in status bar when mouse moves over canvas."""
        coords_text = " Img Coords: --- "
        if self.original_image:
            # Get mouse position relative to canvas widget
            canvas_x = self.canvas.canvasx(event.x)
            canvas_y = self.canvas.canvasy(event.y)
            # Convert to original image coordinates
            img_x, img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
            if img_x is not None and img_y is not None:
                 # Format coordinates, ensuring they are within image bounds visually
                 img_w, img_h = self.original_image.size
                 clamped_x = max(0, min(img_x, img_w))
                 clamped_y = max(0, min(img_y, img_h))
                 coords_text = f" Img Coords: {int(clamped_x):>4}, {int(clamped_y):>4}"

        self.update_status_bar(coords_text=coords_text)
        # Also update the cursor shape based on position (e.g., over resize handles)
        self.update_cursor(event)

    def update_status_bar_selection(self):
        """Updates the selection part ('Sel: WxH px') of the status bar."""
        selection_text = " Sel: --- "
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            # Ensure coords are valid before calculating size
            coords = self.crops[self.selected_crop_id].get('coords')
            if coords and len(coords) == 4:
                 w = coords[2] - coords[0]
                 h = coords[3] - coords[1]
                 # Ensure width and height are non-negative after potential floating point inaccuracies
                 selection_text = f" Sel: {max(0, int(w))}x{max(0, int(h))} px"
            else:
                 print(f"Warning: Invalid coords for selected crop {self.selected_crop_id}")

        self.update_status_bar(selection_text=selection_text)

    # --- Shortcut Handlers ---
    def handle_open_event(self, event=None):
        """Wrapper for Ctrl+O shortcut."""
        # Check if the event originated from an input field to prevent accidental triggers (optional)
        # if isinstance(event.widget, (tk.Entry, ctk.CTkEntry)): return
        self.handle_open()
        return "break" # Prevent further processing of the event

    def handle_open(self):
        """Handles the 'Select Image' action, including unsaved changes check."""
        self.select_image()

    def handle_save_event(self, event=None):
        """Wrapper for Ctrl+S shortcut."""
        # if isinstance(event.widget, (tk.Entry, ctk.CTkEntry)): return
        self.handle_save()
        return "break" # Prevent further processing of the event

    def handle_save(self):
        """Handles the 'Save Crops' action."""
        if self.btn_save_crops.cget("state") == tk.NORMAL: # Check if button is enabled
            self.save_crops()

    def handle_nudge(self, dx_img, dy_img):
        """Nudges the selected crop by dx/dy in image coordinates using Arrow Keys."""
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            crop_id = self.selected_crop_id
            coords = self.crops[crop_id].get('coords')
            if not coords: return # Safety check

            x1, y1, x2, y2 = coords
            new_x1 = x1 + dx_img
            new_y1 = y1 + dy_img
            new_x2 = x2 + dx_img
            new_y2 = y2 + dy_img

            # update_crop_coords handles validation, bounds, and sets dirty flag
            if self.update_crop_coords(crop_id, (new_x1, new_y1, new_x2, new_y2)):
                self.redraw_all_crops() # Redraw to show the nudge
                self.update_status_bar(action_text="Nudged Crop")
                self.update_status_bar_selection()

    def handle_resize_key(self, dx_img, dy_img, handle_direction):
        """Resizes the selected crop from a specific edge/handle using Shift+Arrow Keys."""
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            crop_id = self.selected_crop_id
            coords = self.crops[crop_id].get('coords')
            if not coords: return

            x1, y1, x2, y2 = coords
            nx1, ny1, nx2, ny2 = x1, y1, x2, y2

            # Apply delta based on the handle_direction ('n', 's', 'e', 'w')
            if 'n' in handle_direction: ny1 += dy_img
            if 's' in handle_direction: ny2 += dy_img
            if 'w' in handle_direction: nx1 += dx_img
            if 'e' in handle_direction: nx2 += dx_img

            # update_crop_coords handles validation, min size, bounds, order, and sets dirty flag
            if self.update_crop_coords(crop_id, (nx1, ny1, nx2, ny2)):
                self.redraw_all_crops()
                self.update_status_bar(action_text="Resized Crop")
                self.update_status_bar_selection()

    # --- Image Handling ---
    def select_image(self):
        """Loads a new image, handles unsaved changes, and fits image to view."""
        if not self.check_unsaved_changes():
            return # User cancelled loading new image

        # Ask for image file
        path = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp"),
                       ("All Files", "*.*")]
        )
        if not path:
            self.update_status_bar(action_text="Image Selection Cancelled")
            return # User cancelled file dialog

        self.update_status_bar(action_text="Loading Image...")
        self.update_idletasks() # Ensure status bar updates

        try:
            # Load the image
            new_image = Image.open(path)
            # Ensure it's in a displayable mode (convert if necessary, e.g., from CMYK)
            if new_image.mode == 'CMYK':
                 new_image = new_image.convert('RGB')
            elif new_image.mode == 'P': # Palette mode, convert to RGBA or RGB
                 new_image = new_image.convert('RGBA') # Preserve transparency if any

            self.image_path = path
            self.original_image = new_image

            # Calculate initial fit
            self.update_idletasks() # Ensure canvas size is updated
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            # Use requested size as fallback if actual size is still tiny
            if canvas_width <= 1: canvas_width = self.canvas.winfo_reqwidth()
            if canvas_height <= 1: canvas_height = self.canvas.winfo_reqheight()

            img_width, img_height = self.original_image.size
            if img_width <= 0 or img_height <= 0: raise ValueError("Image has invalid dimensions")

            # Calculate zoom factor to fit image within canvas, without exceeding 100% initially
            zoom_h = (canvas_width / img_width) if img_width > 0 else 1
            zoom_v = (canvas_height / img_height) if img_height > 0 else 1
            initial_zoom = min(zoom_h, zoom_v, 1.0) # Max initial zoom is 100%

            padding_factor = 0.98 # Add a small border around the initially fitted image
            self.zoom_factor = initial_zoom * padding_factor

            # Calculate centering offset
            display_w = img_width * self.zoom_factor
            display_h = img_height * self.zoom_factor
            # Use floor for potentially sharper rendering at 100%? Or ceil? Test needed. Ceil preferred generally.
            self.canvas_offset_x = math.ceil((canvas_width - display_w) / 2)
            self.canvas_offset_y = math.ceil((canvas_height - display_h) / 2)

            # Reset state for the new image
            self.clear_crops_and_list()
            self.next_crop_order_num = 1 # Reset crop numbering
            self.last_saved_to_dir = None # Forget last save directory

            # Display the image
            self.display_image_on_canvas()
            self.btn_save_crops.configure(state=tk.DISABLED) # Disable save until crops are added
            self.set_dirty(False) # Freshly loaded image has no unsaved changes yet
            self.update_status_bar(action_text="Image Loaded Successfully")

        except FileNotFoundError:
            messagebox.showerror("Error", f"Image file not found:\n{path}")
            self.update_status_bar(action_text="Error: File Not Found")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open or process image:\n{e}")
            self.image_path = None
            self.original_image = None
            self.clear_crops_and_list()
            self.canvas.delete("all")
            self.tk_image = None
            self.display_image = None
            self.btn_save_crops.configure(state=tk.DISABLED)
            self.set_dirty(False)
            self.update_status_bar(action_text="Error Loading Image")

    def display_image_on_canvas(self):
        """Displays the current self.display_image on the canvas respecting zoom and pan."""
        if not self.original_image:
            self.canvas.delete("all")
            return

        # Calculate display size based on zoom factor
        disp_w = int(self.original_image.width * self.zoom_factor)
        disp_h = int(self.original_image.height * self.zoom_factor)

        # Ensure minimum display size to avoid errors with tiny zoom factors
        disp_w = max(1, disp_w)
        disp_h = max(1, disp_h)

        try:
            # Use high-quality resizing algorithm
            self.display_image = self.original_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"Error resizing image for display: {e}")
            # Attempt to continue without resizing if error occurs? Or clear canvas?
            self.canvas.delete("all") # Clear canvas on error
            self.update_status_bar(action_text="Error Displaying Image")
            return

        # Convert PIL image to Tkinter PhotoImage
        try:
             self.tk_image = ImageTk.PhotoImage(self.display_image)
        except Exception as e:
             print(f"Error creating PhotoImage: {e}")
             self.canvas.delete("all") # Clear canvas on error
             self.update_status_bar(action_text="Error Displaying Image")
             return

        # Clear previous canvas items (image and rectangles)
        self.canvas.delete("all")

        # Draw the image at the calculated offset (ensure integer coordinates)
        int_offset_x = int(round(self.canvas_offset_x))
        int_offset_y = int(round(self.canvas_offset_y))
        self.canvas_image_id = self.canvas.create_image(
            int_offset_x, int_offset_y,
            anchor=tk.NW, image=self.tk_image, tags="image"
        )

        # Redraw all crop rectangles based on the new view
        self.redraw_all_crops()

    def clear_crops_and_list(self):
        """Clears existing crops from canvas, internal dictionary, and listbox."""
        self.canvas.delete("crop_rect") # Delete only items tagged "crop_rect"
        self.crops.clear()
        self.crop_listbox.delete(0, tk.END)
        self.selected_crop_id = None
        # Disable buttons that require a selection or existing crops
        self.btn_delete_crop.configure(state=tk.DISABLED)
        self.btn_rename_crop.configure(state=tk.DISABLED)
        # Save button state depends on whether crops exist, handled elsewhere
        # Don't reset next_crop_order_num here, only on new image load

    # --- Coordinate Conversion ---
    def canvas_to_image_coords(self, canvas_x, canvas_y):
        """Convert canvas coordinates (relative to canvas 0,0) to original image coordinates."""
        if not self.original_image or self.zoom_factor <= 0: # Prevent division by zero/very small numbers
            return None, None
        img_x = (canvas_x - self.canvas_offset_x) / self.zoom_factor
        img_y = (canvas_y - self.canvas_offset_y) / self.zoom_factor
        return img_x, img_y

    def image_to_canvas_coords(self, img_x, img_y):
        """Convert original image coordinates to canvas coordinates."""
        if not self.original_image:
            return None, None
        canvas_x = (img_x * self.zoom_factor) + self.canvas_offset_x
        canvas_y = (img_y * self.zoom_factor) + self.canvas_offset_y
        return canvas_x, canvas_y

    # --- Crop Handling ---
    def add_crop(self, x1_img, y1_img, x2_img, y2_img):
        """Adds a new crop definition based on image coordinates, draws it, and selects it."""
        if not self.original_image: return

        # Validate coordinates against image dimensions and minimum size
        img_w, img_h = self.original_image.size
        # Clamp coordinates to be within image bounds
        x1_img = max(0, min(x1_img, img_w))
        y1_img = max(0, min(y1_img, img_h))
        x2_img = max(0, min(x2_img, img_w))
        y2_img = max(0, min(y2_img, img_h))

        # Ensure coordinates are ordered (x1 < x2, y1 < y2)
        coords = (min(x1_img, x2_img), min(y1_img, y2_img),
                  max(x1_img, x2_img), max(y1_img, y2_img))

        # Check for minimum size after ordering and clamping
        if (coords[2] - coords[0]) < MIN_CROP_SIZE or \
           (coords[3] - coords[1]) < MIN_CROP_SIZE:
            print("Crop too small, ignoring.")
            # Clean up temporary drawing rectangle if it exists
            if self.current_rect_id and self.current_rect_id in self.canvas.find_withtag("temp_rect"):
                self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            self.update_status_bar(action_text="Crop Too Small")
            return

        # Generate unique ID and default name
        crop_id = str(uuid.uuid4())
        crop_name = f"Crop_{self.next_crop_order_num}"
        current_order_num = self.next_crop_order_num
        self.next_crop_order_num += 1

        # Convert valid image coordinates back to canvas coordinates for drawing
        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])
        if cx1 is None: # Coordinate conversion failed
            print("Error: Cannot draw crop, coordinate conversion failed.")
            self.update_status_bar(action_text="Error Adding Crop")
            return

        # Draw the rectangle on the canvas (initially selected style)
        rect_id = self.canvas.create_rectangle(
            cx1, cy1, cx2, cy2,
            outline=SELECTED_RECT_COLOR, width=SELECTED_RECT_WIDTH, # Created selected
            tags=(RECT_TAG_PREFIX + crop_id, "crop_rect")
        )

        # Store crop data including the original creation order
        self.crops[crop_id] = {
            'coords': coords, # Store ORIGINAL image coordinates
            'name': crop_name,
            'rect_id': rect_id,
            'order': current_order_num
        }

        # Add name to the listbox
        self.crop_listbox.insert(tk.END, crop_name)
        # Select the newly added item in the listbox
        self.crop_listbox.selection_clear(0, tk.END)
        self.crop_listbox.selection_set(tk.END)
        self.crop_listbox.activate(tk.END)
        self.crop_listbox.see(tk.END) # Ensure it's visible

        # Update internal selection state (will also update status bar)
        self.select_crop(crop_id, from_listbox=False)

        # Enable relevant buttons and mark unsaved changes
        self.btn_save_crops.configure(state=tk.NORMAL)
        # Delete/Rename state handled by select_crop
        self.set_dirty()
        self.update_status_bar(action_text="Crop Added")

    def select_crop(self, crop_id, from_listbox=True):
        """Selects a crop by its ID, updates visuals and button states."""
        if self.selected_crop_id == crop_id and crop_id is not None:
            self.update_status_bar_selection() # Update selection info just in case
            return # Already selected

        # Deselect previous rectangle visually
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            prev_data = self.crops[self.selected_crop_id]
            prev_rect_id = prev_data.get('rect_id')
            # Check if the previous rectangle still exists on the canvas
            if prev_rect_id and prev_rect_id in self.canvas.find_withtag(prev_rect_id):
                 self.canvas.itemconfig(prev_rect_id, outline=DEFAULT_RECT_COLOR, width=RECT_WIDTH)

        # Update internal selection ID
        self.selected_crop_id = crop_id

        # Select new rectangle visually and update UI state
        if crop_id and crop_id in self.crops:
            data = self.crops[crop_id]
            rect_id = data.get('rect_id')
            # Check if the new rectangle exists on the canvas
            if rect_id and rect_id in self.canvas.find_withtag(rect_id):
                 self.canvas.itemconfig(rect_id, outline=SELECTED_RECT_COLOR, width=SELECTED_RECT_WIDTH)
                 self.canvas.tag_raise(rect_id) # Bring selected rectangle to front
                 self.btn_delete_crop.configure(state=tk.NORMAL)
                 self.btn_rename_crop.configure(state=tk.NORMAL)

                 # Update listbox selection if this call didn't originate from the listbox
                 if not from_listbox:
                     index = -1
                     for i in range(self.crop_listbox.size()):
                         if self.crop_listbox.get(i) == data.get('name'):
                             index = i
                             break
                     if index != -1:
                         self.crop_listbox.selection_clear(0, tk.END)
                         self.crop_listbox.selection_set(index)
                         self.crop_listbox.activate(index)
                         self.crop_listbox.see(index)
            else:
                 # Rectangle ID is invalid (e.g., after image reload/clear but before redraw)
                 print(f"Warning: Stale rectangle ID {rect_id} for crop {crop_id}")
                 self.selected_crop_id = None # Mark as deselected internally
                 self.btn_delete_crop.configure(state=tk.DISABLED)
                 self.btn_rename_crop.configure(state=tk.DISABLED)
        else:
            # No valid crop selected or crop_id is None (deselection)
            self.selected_crop_id = None
            if not from_listbox: # If deselection wasn't from listbox click, clear listbox selection
                self.crop_listbox.selection_clear(0, tk.END)
            self.btn_delete_crop.configure(state=tk.DISABLED)
            self.btn_rename_crop.configure(state=tk.DISABLED)

        # Update the status bar with current selection info (or lack thereof)
        self.update_status_bar_selection()

    def update_crop_coords(self, crop_id, new_img_coords):
        """
        Updates the stored original image coordinates for a crop after validation.
        Sets the dirty flag if coordinates actually change.
        Returns True if update was successful (even if no change), False otherwise.
        """
        if crop_id in self.crops and self.original_image:
            img_w, img_h = self.original_image.size
            x1, y1, x2, y2 = new_img_coords

            # Clamp coordinates to image bounds
            x1 = max(0, min(x1, img_w))
            y1 = max(0, min(y1, img_h))
            x2 = max(0, min(x2, img_w))
            y2 = max(0, min(y2, img_h))

            # Ensure order (x1 < x2, y1 < y2)
            final_x1 = min(x1, x2)
            final_y1 = min(y1, y2)
            final_x2 = max(x1, x2)
            final_y2 = max(y1, y2)

            # Check minimum size
            if (final_x2 - final_x1) < MIN_CROP_SIZE or \
               (final_y2 - final_y1) < MIN_CROP_SIZE:
                # print("Debug: Crop update rejected due to min size violation")
                return False # Update failed validation

            new_coords_tuple = (final_x1, final_y1, final_x2, final_y2)

            # Check if coordinates actually changed
            if self.crops[crop_id]['coords'] != new_coords_tuple:
                 self.crops[crop_id]['coords'] = new_coords_tuple
                 self.set_dirty() # Set dirty flag only if coordinates changed
                 return True
            else:
                 return True # Coordinates are valid but didn't change, still successful

        return False # Crop ID not found or no original image

    def redraw_all_crops(self):
        """Redraws all crop rectangles based on stored coords, current view, and selection state."""
        all_canvas_items = self.canvas.find_all() # Get current items once for efficiency

        for crop_id, data in self.crops.items():
            coords = data.get('coords')
            rect_id = data.get('rect_id')
            if not coords or len(coords) != 4: continue # Skip if invalid data

            img_x1, img_y1, img_x2, img_y2 = coords
            # Convert image coords to canvas coords for current view
            cx1, cy1 = self.image_to_canvas_coords(img_x1, img_y1)
            cx2, cy2 = self.image_to_canvas_coords(img_x2, img_y2)

            if cx1 is None: continue # Skip if conversion failed

            # Determine visual style based on selection state
            is_selected = (crop_id == self.selected_crop_id)
            color = SELECTED_RECT_COLOR if is_selected else DEFAULT_RECT_COLOR
            width = SELECTED_RECT_WIDTH if is_selected else RECT_WIDTH
            tags_tuple = (RECT_TAG_PREFIX + crop_id, "crop_rect") # Ensure tags are tuple

            # Check if the rectangle item already exists on the canvas
            if rect_id and rect_id in all_canvas_items:
                 # If rectangle exists, update its coordinates and visual style
                 self.canvas.coords(rect_id, cx1, cy1, cx2, cy2)
                 self.canvas.itemconfig(rect_id, outline=color, width=width, tags=tags_tuple)
            else:
                 # If rectangle doesn't exist (e.g., after image reload), recreate it
                 # print(f"Debug: Recreating rectangle for crop {crop_id}")
                 new_rect_id = self.canvas.create_rectangle(
                     cx1, cy1, cx2, cy2,
                     outline=color, width=width,
                     tags=tags_tuple
                 )
                 # Update the stored rect_id for this crop
                 self.crops[crop_id]['rect_id'] = new_rect_id

        # Ensure the currently selected rectangle is drawn on top of others
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            selected_rect_id = self.crops[self.selected_crop_id].get('rect_id')
            if selected_rect_id and selected_rect_id in self.canvas.find_all(): # Check if exists before raising
                 self.canvas.tag_raise(selected_rect_id)

        # Update selection info in status bar after redraw completes
        self.update_status_bar_selection()

    def delete_selected_crop_event(self, event=None):
        """Wrapper for Delete key shortcut."""
        # Prevent delete if focus is on an entry widget (e.g., rename dialog)
        # if isinstance(self.focus_get(), (tk.Entry, ctk.CTkEntry)):
        #     return
        self.delete_selected_crop()
        return "break" # Prevent further processing if needed

    def delete_selected_crop(self):
        """Deletes the currently selected crop."""
        if not self.selected_crop_id or self.selected_crop_id not in self.crops:
            return

        crop_id_to_delete = self.selected_crop_id
        data = self.crops[crop_id_to_delete]
        rect_id = data.get('rect_id')
        current_name = data.get('name')

        # Remove rectangle from canvas (check existence first)
        if rect_id and rect_id in self.canvas.find_all():
             self.canvas.delete(rect_id)

        # Find listbox index based on the name *before* deleting the crop data
        index_to_delete = -1
        if current_name:
             for i in range(self.crop_listbox.size()):
                 if self.crop_listbox.get(i) == current_name:
                     index_to_delete = i
                     break

        # Remove crop data from internal dictionary
        del self.crops[crop_id_to_delete]

        # Remove name from listbox if found
        if index_to_delete != -1:
            self.crop_listbox.delete(index_to_delete)

        # Reset selection state and update UI
        self.selected_crop_id = None
        self.btn_delete_crop.configure(state=tk.DISABLED)
        self.btn_rename_crop.configure(state=tk.DISABLED)
        if not self.crops: # If no crops left, disable save button
             self.btn_save_crops.configure(state=tk.DISABLED)

        self.set_dirty() # Mark changes as unsaved
        self.update_status_bar(action_text="Crop Deleted")

        # Select the next item in the list if possible (select previous visually)
        if self.crop_listbox.size() > 0:
            new_index = max(0, index_to_delete - 1) # Try selecting previous item
            # Adjust if the deleted item was the first one or listbox index was not found
            if index_to_delete == 0 or index_to_delete == -1:
                 new_index = 0
            # Adjust if the deleted item was the last one
            if new_index >= self.crop_listbox.size():
                 new_index = self.crop_listbox.size() - 1

            self.crop_listbox.selection_set(new_index)
            self.on_listbox_select() # Trigger selection logic for the new selection
        else:
            # No items left, ensure everything is visually deselected
            self.crop_listbox.selection_clear(0, tk.END)
            self.select_crop(None, from_listbox=False) # Explicitly deselect internal state and update status

    # --- Rename Crop ---
    def prompt_rename_selected_crop_event(self, event=None):
        """Handles double-click event on listbox for renaming."""
        self.prompt_rename_selected_crop()

    def prompt_rename_selected_crop(self):
        """Shows a dialog to rename the selected crop."""
        if not self.selected_crop_id or self.selected_crop_id not in self.crops:
            messagebox.showwarning("Rename Error", "Please select a crop from the list to rename.", parent=self)
            return

        crop_id = self.selected_crop_id
        current_name = self.crops[crop_id].get('name', '')

        # Use CTkInputDialog for consistent look and feel
        dialog = ctk.CTkInputDialog(text=f"Enter new name for '{current_name}':", title="Rename Crop",
                                    entry_fg_color="white", entry_text_color="black") # Adjust colors for light theme if needed
        # Position dialog relative to the main window
        dialog.geometry(f"+{self.winfo_x()+200}+{self.winfo_y()+200}")
        new_name_raw = dialog.get_input() # Returns the input string or None if cancelled

        if new_name_raw is None or not new_name_raw.strip():
            self.update_status_bar(action_text="Rename Cancelled")
            return # User cancelled or entered empty name

        new_name = new_name_raw.strip()

        # Check for duplicate names (important for saving files later)
        for c_id, data in self.crops.items():
            if c_id != crop_id and data.get('name') == new_name:
                messagebox.showerror("Rename Error", f"A crop named '{new_name}' already exists. Please choose a unique name.", parent=self)
                return

        # Update internal data
        self.crops[crop_id]['name'] = new_name

        # Update listbox display
        index = -1
        for i in range(self.crop_listbox.size()):
            # Find by iterating, as selection might be out of sync briefly
            # We need the actual index of the item corresponding to the selected crop ID
            lb_name = self.crop_listbox.get(i)
            # Find the crop ID associated with this listbox name
            lb_crop_id = None
            for temp_id, temp_data in self.crops.items():
                 # Use the NEW name for the current crop, OLD name for others
                 name_to_check = temp_data.get('name') if temp_id != crop_id else current_name
                 if temp_data.get('name') == lb_name: # This logic might be complex if names aren't unique during transition
                      pass # Simpler: find the index of the OLD name
            if lb_name == current_name: # Find index based on the name *before* the update
                index = i
                break

        if index != -1:
            self.crop_listbox.delete(index)
            self.crop_listbox.insert(index, new_name) # Insert new name at the same position
            self.crop_listbox.selection_set(index)    # Re-select the item in the listbox
            self.crop_listbox.activate(index)

        self.set_dirty() # Mark changes as unsaved
        self.update_status_bar(action_text="Crop Renamed")

    # --- Mouse Events ---
    def on_mouse_press(self, event):
        """Handles left mouse button press on the canvas."""
        self.canvas.focus_set() # Allow canvas to receive keyboard events (like Delete)
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        action_text = "Ready" # Default status

        # 1. Check for resize handle click on the selected crop
        handle = self.get_resize_handle(canvas_x, canvas_y)
        if handle and self.selected_crop_id:
            self.is_resizing = True
            self.resize_handle = handle
            self.start_x, self.start_y = canvas_x, canvas_y
            # Store original image coordinates *before* resizing starts for accurate delta calculation
            self.start_coords_img = self.crops[self.selected_crop_id].get('coords')
            action_text = "Resizing Crop..."
            self.update_status_bar(action_text=action_text)
            return # Don't proceed to other checks

        # 2. Check for click inside an existing crop rectangle (select/move)
        # Find items near the click, check top-most tagged 'crop_rect'
        overlapping_items = self.canvas.find_overlapping(canvas_x-1, canvas_y-1, canvas_x+1, canvas_y+1)
        clicked_crop_id = None
        for item_id in reversed(overlapping_items): # Check topmost item first
            tags = self.canvas.gettags(item_id)
            if tags and tags[0].startswith(RECT_TAG_PREFIX) and "crop_rect" in tags:
                crop_id = tags[0][len(RECT_TAG_PREFIX):]
                if crop_id in self.crops: # Verify the found ID is valid
                    clicked_crop_id = crop_id
                    break # Found the topmost valid crop rectangle

        if clicked_crop_id:
            # Select the clicked crop (select_crop handles visual changes and status bar update)
            self.select_crop(clicked_crop_id)
            # Prepare for moving
            self.is_moving = True
            rect_coords = self.canvas.coords(self.crops[clicked_crop_id]['rect_id'])
            # Calculate mouse offset relative to the top-left corner for smooth dragging
            self.move_offset_x = canvas_x - rect_coords[0]
            self.move_offset_y = canvas_y - rect_coords[1]
            self.start_coords_img = self.crops[clicked_crop_id].get('coords') # Store start coords for move validation if needed
            action_text = "Moving Crop..."
            self.update_status_bar(action_text=action_text)
            return # Don't start drawing

        # 3. If not resizing or moving, start drawing a new rectangle (if image loaded)
        if self.original_image:
            self.is_drawing = True
            self.start_x, self.start_y = canvas_x, canvas_y
            # Create a temporary dashed rectangle for visual feedback
            self.current_rect_id = self.canvas.create_rectangle(
                self.start_x, self.start_y, self.start_x, self.start_y,
                outline=SELECTED_RECT_COLOR, width=RECT_WIDTH, dash=(4, 4),
                tags=("temp_rect",) # Tag for easy deletion
            )
            # Deselect any currently selected crop
            self.select_crop(None)
            action_text = "Drawing Crop..."
            self.update_status_bar(action_text=action_text)

    def on_mouse_drag(self, event):
        """Handles left mouse button drag on the canvas."""
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self.is_drawing and self.current_rect_id:
            # Update the temporary drawing rectangle
            self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, canvas_x, canvas_y)

        elif self.is_moving and self.selected_crop_id:
            crop_id = self.selected_crop_id
            rect_id = self.crops[crop_id]['rect_id']
            # Calculate new top-left canvas position based on mouse and initial offset
            new_cx1 = canvas_x - self.move_offset_x
            new_cy1 = canvas_y - self.move_offset_y
            # Get current rectangle dimensions on canvas
            current_canvas_coords = self.canvas.coords(rect_id)
            w = current_canvas_coords[2] - current_canvas_coords[0]
            h = current_canvas_coords[3] - current_canvas_coords[1]
            new_cx2 = new_cx1 + w
            new_cy2 = new_cy1 + h

            # Convert new canvas coords back to original image coords for validation/storage
            img_x1, img_y1 = self.canvas_to_image_coords(new_cx1, new_cy1)
            img_x2, img_y2 = self.canvas_to_image_coords(new_cx2, new_cy2)

            if img_x1 is not None: # Check conversion was successful
                # Update stored coordinates (includes bounds check, sets dirty flag)
                if self.update_crop_coords(crop_id, (img_x1, img_y1, img_x2, img_y2)):
                    # Redraw using validated coordinates to handle boundary snapping etc.
                    self.redraw_all_crops()
                    self.update_status_bar_selection() # Update size display in status bar

        elif self.is_resizing and self.selected_crop_id and self.resize_handle and self.start_coords_img:
            crop_id = self.selected_crop_id
            # Use the stored coords *before* the resize started as the base
            ox1_img, oy1_img, ox2_img, oy2_img = self.start_coords_img

            # Convert current mouse canvas coords to image coords
            curr_img_x, curr_img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
            # Convert starting mouse canvas coords to image coords
            start_img_x_conv, start_img_y_conv = self.canvas_to_image_coords(self.start_x, self.start_y)

            if curr_img_x is None or start_img_x_conv is None: return # Bail if conversion fails

            # Calculate mouse delta in image coordinates
            dx_img = curr_img_x - start_img_x_conv
            dy_img = curr_img_y - start_img_y_conv

            nx1, ny1, nx2, ny2 = ox1_img, oy1_img, ox2_img, oy2_img

            # Apply delta based on the handle being dragged
            if 'n' in self.resize_handle: ny1 += dy_img
            if 's' in self.resize_handle: ny2 += dy_img
            if 'w' in self.resize_handle: nx1 += dx_img
            if 'e' in self.resize_handle: nx2 += dx_img

            # Update stored coords (includes validation: min size, bounds, order, sets dirty flag)
            if self.update_crop_coords(crop_id, (nx1, ny1, nx2, ny2)):
                 # Redraw using validated coordinates
                 self.redraw_all_crops()
                 self.update_status_bar_selection() # Update size display in status bar

    def on_mouse_release(self, event):
        """Handles left mouse button release on the canvas."""
        if self.is_drawing and self.current_rect_id:
            # Finalize the new crop
            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            # Delete the temporary dashed rectangle (check existence first)
            if self.current_rect_id in self.canvas.find_withtag("temp_rect"):
                 self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None # Clear temp rect ID

            # Convert start and end canvas coords to image coords
            img_x1, img_y1 = self.canvas_to_image_coords(self.start_x, self.start_y)
            img_x2, img_y2 = self.canvas_to_image_coords(canvas_x, canvas_y)

            # Add the crop if coordinates are valid
            if img_x1 is not None and img_y1 is not None and img_x2 is not None and img_y2 is not None:
                 self.add_crop(img_x1, img_y1, img_x2, img_y2) # add_crop handles selection and status
            else:
                 print("Failed to add crop due to coordinate conversion error.")
                 self.update_status_bar(action_text="Error Adding Crop")

        # Reset states after any action (draw, move, resize)
        self.is_drawing, self.is_moving, self.is_resizing = False, False, False
        self.resize_handle = None
        self.start_x, self.start_y = None, None # Clear start coords
        self.start_coords_img = None
        self.update_cursor(event) # Update cursor based on final position
        # Set status back to Ready unless add_crop set it
        if not (self.is_drawing and self.current_rect_id is None): # Avoid overwriting "Crop Added" status
             self.update_status_bar(action_text="Ready")

    # --- Zoom and Pan ---
    def on_mouse_wheel(self, event, direction=None):
        """Handles mouse wheel scrolling for zooming."""
        if not self.original_image: return

        # Determine scroll direction (platform differences)
        delta = 0
        if direction: # Linux binding provides direction
            delta = direction
        elif event.num == 5 or event.delta < 0: # Scroll down/away
            delta = -1
        elif event.num == 4 or event.delta > 0: # Scroll up/towards
            delta = 1
        else:
            return # Unknown scroll event

        # Define zoom parameters
        zoom_increment = 1.1
        min_zoom = 0.01 # Allow zooming out significantly
        max_zoom = 25.0 # Set a reasonable maximum zoom

        # Get mouse position on canvas - this is the zoom center
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)

        # Calculate what point on the *original image* is under the mouse *before* zoom
        img_x_before, img_y_before = self.canvas_to_image_coords(canvas_x, canvas_y)
        if img_x_before is None: return # Cannot zoom if mouse is outside image area

        # Calculate new zoom factor
        if delta > 0: # Zoom in
            new_zoom = self.zoom_factor * zoom_increment
        else: # Zoom out
            new_zoom = self.zoom_factor / zoom_increment
        # Clamp zoom factor within limits
        new_zoom = max(min_zoom, min(max_zoom, new_zoom))

        if abs(new_zoom - self.zoom_factor) < 0.0001: return # No significant change

        # Store the new zoom factor
        old_zoom = self.zoom_factor
        self.zoom_factor = new_zoom

        # Calculate the new canvas offset to keep the point under the mouse stationary
        # Formula: new_offset = mouse_canvas_pos - (image_point_before_zoom * new_zoom_factor)
        self.canvas_offset_x = canvas_x - (img_x_before * self.zoom_factor)
        self.canvas_offset_y = canvas_y - (img_y_before * self.zoom_factor)

        # Update the displayed image and redraw crops at the new scale/position
        self.display_image_on_canvas()
        # Update status bar immediately
        self.update_status_bar(action_text=f"Zoom {('In' if delta > 0 else 'Out')}")

    def on_pan_press(self, event):
        """Handles middle mouse button press to start panning."""
        if not self.original_image: return
        self.is_panning = True
        # Record the starting mouse position on the canvas
        self.pan_start_x = self.canvas.canvasx(event.x)
        self.pan_start_y = self.canvas.canvasy(event.y)
        # Change cursor to indicate panning
        self.canvas.config(cursor="fleur")
        self.update_status_bar(action_text="Panning...")

    def on_pan_drag(self, event):
        """Handles middle mouse button drag to pan the image."""
        if not self.is_panning or not self.original_image: return
        current_x = self.canvas.canvasx(event.x)
        current_y = self.canvas.canvasy(event.y)

        # Calculate the distance moved since the last drag event
        dx = current_x - self.pan_start_x
        dy = current_y - self.pan_start_y

        # Update the canvas offset (where the image's top-left corner is)
        self.canvas_offset_x += dx
        self.canvas_offset_y += dy

        # Move all items on the canvas (image and rectangles) by the delta
        self.canvas.move("all", dx, dy)

        # Update the starting position for the *next* drag event
        self.pan_start_x = current_x
        self.pan_start_y = current_y

    def on_pan_release(self, event):
        """Handles middle mouse button release to stop panning."""
        self.is_panning = False
        # Reset cursor based on current position (might be over a handle, etc.)
        self.update_cursor(event)
        self.update_status_bar(action_text="Ready")

    # --- Listbox Selection ---
    def on_listbox_select(self, event=None):
        """Handles selection changes in the crop listbox."""
        selection = self.crop_listbox.curselection() # Get tuple of selected indices
        selected_id = None
        if selection:
            selected_index = selection[0]
            selected_name = self.crop_listbox.get(selected_index)
            # Find the crop_id associated with the selected name
            for crop_id, data in self.crops.items():
                if data.get('name') == selected_name:
                    selected_id = crop_id
                    break
        # Call select_crop which handles visual updates, button states, and status bar
        self.select_crop(selected_id, from_listbox=True)

    # --- Resizing Helpers & Cursor ---
    def get_resize_handle(self, canvas_x, canvas_y):
        """Checks if the canvas coordinates are near a resize handle of the selected crop."""
        if not self.selected_crop_id or self.selected_crop_id not in self.crops:
            return None

        rect_id = self.crops[self.selected_crop_id].get('rect_id')
        # Check if rect_id is valid before getting coords
        if not rect_id or rect_id not in self.canvas.find_all():
            return None

        cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
        handle_margin = 8 # Pixel tolerance around edges/corners for handle detection

        # Check corners first (larger detection area)
        if abs(canvas_x - cx1) < handle_margin and abs(canvas_y - cy1) < handle_margin: return 'nw'
        if abs(canvas_x - cx2) < handle_margin and abs(canvas_y - cy1) < handle_margin: return 'ne'
        if abs(canvas_x - cx1) < handle_margin and abs(canvas_y - cy2) < handle_margin: return 'sw'
        if abs(canvas_x - cx2) < handle_margin and abs(canvas_y - cy2) < handle_margin: return 'se'

        # Check edges if not on corner
        # Add a small inner buffer relative to margin to avoid edge detection when clearly inside
        inner_buffer = handle_margin / 2
        # Check N edge: y near cy1, x between corners (+buffer)
        if abs(canvas_y - cy1) < handle_margin and (cx1 + inner_buffer) < canvas_x < (cx2 - inner_buffer): return 'n'
        # Check S edge: y near cy2, x between corners (+buffer)
        if abs(canvas_y - cy2) < handle_margin and (cx1 + inner_buffer) < canvas_x < (cx2 - inner_buffer): return 's'
        # Check W edge: x near cx1, y between corners (+buffer)
        if abs(canvas_x - cx1) < handle_margin and (cy1 + inner_buffer) < canvas_y < (cy2 - inner_buffer): return 'w'
        # Check E edge: x near cx2, y between corners (+buffer)
        if abs(canvas_x - cx2) < handle_margin and (cy1 + inner_buffer) < canvas_y < (cy2 - inner_buffer): return 'e'

        return None # Not near any handle

    def update_cursor(self, event=None):
        """Changes the mouse cursor based on position relative to selected crop handles or interior."""
        # Prioritize cursors for active states
        if self.is_panning or self.is_moving:
            new_cursor = "fleur"
        elif self.is_resizing:
            # Set cursor based on the active resize handle
            handle = self.resize_handle
            if handle in ('nw', 'se'): new_cursor = "size_nw_se"
            elif handle in ('ne', 'sw'): new_cursor = "size_ne_sw"
            elif handle in ('n', 's'): new_cursor = "size_ns"
            elif handle in ('e', 'w'): new_cursor = "size_we"
            else: new_cursor = "" # Default if handle is somehow invalid
        elif self.is_drawing:
            new_cursor = "crosshair"
        else:
            # Check hover state if not actively doing something
            new_cursor = "" # Default arrow cursor
            if event:
                canvas_x = self.canvas.canvasx(event.x)
                canvas_y = self.canvas.canvasy(event.y)
                handle = self.get_resize_handle(canvas_x, canvas_y)

                if handle:
                    # Map handle to appropriate Tk cursor names for hover
                    if handle in ('nw', 'se'): new_cursor = "size_nw_se"
                    elif handle in ('ne', 'sw'): new_cursor = "size_ne_sw"
                    elif handle in ('n', 's'): new_cursor = "size_ns"
                    elif handle in ('e', 'w'): new_cursor = "size_we"
                else:
                    # Check if hovering inside the *selected* rectangle to indicate movability
                    if self.selected_crop_id and self.selected_crop_id in self.crops:
                        rect_id = self.crops[self.selected_crop_id].get('rect_id')
                        if rect_id and rect_id in self.canvas.find_all(): # Check valid id
                            cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
                            # Check if mouse is strictly inside the bounds (not on edge where handle detection happens)
                            margin = 1 # Small margin to differentiate from edge/handle hover
                            if (cx1 + margin) < canvas_x < (cx2 - margin) and \
                               (cy1 + margin) < canvas_y < (cy2 - margin):
                                new_cursor = "fleur" # Indicate movability

        # Only update the canvas cursor if it needs to change
        if self.canvas.cget("cursor") != new_cursor:
             self.canvas.config(cursor=new_cursor)

    # --- Window Resize Handling ---
    def on_window_resize(self, event=None):
        """Handles window resize events. Could potentially refit image if desired."""
        # Currently, we just let the canvas resize. Zoom/Pan allows user adjustment.
        # To refit image automatically on resize:
        # 1. Add a small delay using self.after() to avoid excessive calls during resize drag.
        # 2. In the delayed function, recalculate initial fit based on new canvas size
        #    and call display_image_on_canvas(). This might be jarring for users.
        pass

    # --- Saving Crops ---
    def save_crops(self):
        """Saves all defined crops to a user-selected directory."""
        if not self.original_image or not self.image_path:
            messagebox.showwarning("Save Error", "Cannot save - No image loaded.", parent=self)
            return
        if not self.crops:
            messagebox.showwarning("Save Error", "Cannot save - No crops defined.", parent=self)
            return

        # Ask user for the output directory
        initial_dir = self.last_saved_to_dir # Start in last used directory
        # Default suggestion: a folder named after the image, located in the image's original directory
        if not initial_dir:
            img_dir = os.path.dirname(self.image_path)
            base_name = os.path.splitext(os.path.basename(self.image_path))[0]
            initial_dir = os.path.join(img_dir, base_name)

        output_dir = filedialog.askdirectory(
            parent=self, # Make dialog modal to this app window
            title="Select Folder to Save Cropped Images",
            initialdir=initial_dir # Suggest last used or default folder
            # mustexist=True # askdirectory ensures this by default
        )

        if not output_dir: # User cancelled the directory selection
            self.update_status_bar(action_text="Save Cancelled")
            return

        self.last_saved_to_dir = output_dir # Remember the chosen directory for next time

        # Update status bar to indicate saving process
        self.update_status_bar(action_text="Saving Crops...")
        self.update_idletasks() # Ensure UI updates immediately

        saved_count = 0
        error_count = 0
        error_messages = []

        # Sort crops by their original creation order number for sequential file naming if desired
        # Although filenames now use custom names, saving in order might still be preferred.
        def get_crop_order(item_tuple):
            crop_id, data = item_tuple
            return data.get('order', float('inf')) # Use stored order number, fallback if missing

        sorted_crop_items = sorted(self.crops.items(), key=get_crop_order)

        for i, (crop_id, data) in enumerate(sorted_crop_items):
            coords = data.get('coords')
            crop_name = data.get('name', f'Unnamed_Crop_{i+1}')
            if not coords:
                error_count += 1
                error_messages.append(f"Skipping '{crop_name}': Invalid coordinate data.")
                continue

            # Sanitize the crop name to create a valid filename
            # Remove/replace characters invalid in Windows filenames: \ / : * ? " < > |
            safe_crop_name = re.sub(r'[\\/*?:"<>|]', '_', crop_name)
            # Avoid names ending with space or period (also problematic on Windows)
            safe_crop_name = safe_crop_name.rstrip('. ')
            if not safe_crop_name: # Handle cases where name becomes empty after sanitizing
                 safe_crop_name = f"Crop_{data.get('order', i+1)}"

            filename = f"{safe_crop_name}.jpg" # Save as JPG using the (sanitized) crop name
            filepath = os.path.join(output_dir, filename)

            # Ensure coordinates are integers for Pillow's crop function
            int_coords = tuple(map(int, coords))

            try:
                # Crop the *original* image using the validated integer coordinates
                cropped_img = self.original_image.crop(int_coords)

                # Convert to RGB before saving as JPG if necessary (e.g., if original has alpha)
                if cropped_img.mode in ('RGBA', 'P', 'LA'):
                    # Create a white background image of the same size
                    bg = Image.new("RGB", cropped_img.size, (255, 255, 255))
                    # Paste the potentially transparent image onto the white background
                    # The original image itself is used as the mask for pasting if it has alpha
                    bg.paste(cropped_img, mask=cropped_img.split()[-1] if 'A' in cropped_img.mode else None)
                    cropped_img = bg # Now it's an RGB image
                elif cropped_img.mode != 'RGB':
                    cropped_img = cropped_img.convert('RGB') # Convert other modes like L

                # Save the cropped image as JPG
                cropped_img.save(filepath, "JPEG", quality=95, optimize=True) # Adjust quality as needed
                saved_count += 1

            except Exception as e:
                error_count += 1
                err_msg = f"Error saving '{filename}': {e}"
                print(err_msg) # Log detailed error to console
                error_messages.append(err_msg)

        # Show summary message after attempting to save all crops
        if error_count == 0:
            self.set_dirty(False) # Clear unsaved changes flag on complete success
            messagebox.showinfo("Success", f"Successfully saved {saved_count} crops to:\n{output_dir}", parent=self)
            self.update_status_bar(action_text="Crops Saved Successfully")
        else:
            # Decide if partial success should clear dirty flag? Probably not.
            error_summary = "\n - ".join(error_messages[:3]) # Show first few errors
            if len(error_messages) > 3: error_summary += "\n   (...more errors in console)"
            messagebox.showwarning("Partial Success",
                                   f"Saved {saved_count} crops to:\n{output_dir}\n\nFailed to save {error_count} crops:\n - {error_summary}",
                                   parent=self)
            self.update_status_bar(action_text="Save Complete (with errors)")

# --- Run the Application ---
if __name__ == "__main__":
    # Ensure high-DPI awareness if running on Windows
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1) # Set awareness for the process
    except ImportError: # Not Windows or ctypes not available
        pass
    except Exception as e: # Catch other potential errors during DPI awareness setting
        print(f"Could not set DPI awareness: {e}")

    app = MultiCropApp()
    app.mainloop()
