# -*- coding: utf-8 -*-
"""
Multi Crop App Refactored
A simple Windows application to select multiple rectangular regions (crops)
from an image and export them simultaneously.

Refactoring Improvements:
- Uses a dedicated Crop dataclass.
- Separates Canvas interaction logic into a helper class.
- Manages crop data and listbox updates within a CropManager class.
- Centralizes coordinate conversion.
- Improves readability of mouse event handlers and save logic.
- Better state management for drawing/moving/resizing.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, Listbox
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import uuid
import math
import re
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, Any

# --- Constants ---
RECT_TAG_PREFIX = "crop_rect_"
TEMP_RECT_TAG = "temp_rect"
IMAGE_TAG = "image"
CROP_RECT_COMMON_TAG = "crop_rect" # Tag used for all crop rectangles
DEFAULT_RECT_COLOR = "red"
SELECTED_RECT_COLOR = "blue"
RECT_WIDTH = 2
SELECTED_RECT_WIDTH = 3 # Make selected rectangle thicker
MIN_CROP_SIZE = 10 # Minimum width/height for a crop in image pixels (in original image pixels)
APP_NAME = "Multi Image Cropper"
HANDLE_SIZE = 8 # Size of the resize handles on the canvas

# --- Data Structures ---
@dataclass
class Crop:
    """Represents a single crop area."""
    id: str # Unique identifier
    coords: Tuple[int, int, int, int] # (x1, y1, x2, y2) in original image pixels
    name: str
    order: int # Sequential number for default naming
    rect_id: Optional[int] = None # Canvas item ID for the rectangle

# --- Helper Classes ---

class CoordinateConverter:
    """Handles conversion between canvas and image coordinates, considering zoom and pan."""
    def __init__(self):
        self.image_size: Tuple[int, int] = (0, 0) # (width, height)
        self.zoom_factor: float = 1.0
        self.canvas_offset_x: float = 0.0
        self.canvas_offset_y: float = 0.0

    def set_image_data(self, img_width: int, img_height: int):
        """Set the original image dimensions."""
        self.image_size = (img_width, img_height)

    def set_zoom_pan(self, zoom_factor: float, offset_x: float, offset_y: float):
        """Set the current zoom level and canvas pan offset."""
        self.zoom_factor = zoom_factor
        self.canvas_offset_x = offset_x
        self.canvas_offset_y = offset_y

    def canvas_to_image(self, cx: float, cy: float) -> Optional[Tuple[float, float]]:
        """Convert canvas coordinates to original image coordinates."""
        if self.zoom_factor <= 0 or self.image_size[0] <= 0 or self.image_size[1] <= 0:
            return None
        ix = (cx - self.canvas_offset_x) / self.zoom_factor
        iy = (cy - self.canvas_offset_y) / self.zoom_factor
        return ix, iy

    def image_to_canvas(self, ix: float, iy: float) -> Optional[Tuple[float, float]]:
        """Convert original image coordinates to canvas coordinates."""
        if self.image_size[0] <= 0 or self.image_size[1] <= 0:
             return None
        cx = (ix * self.zoom_factor) + self.canvas_offset_x
        cy = (iy * self.zoom_factor) + self.canvas_offset_y
        return cx, cy

    def image_rect_to_canvas(self, rect_img: Tuple[int, int, int, int]) -> Optional[Tuple[float, float, float, float]]:
        """Convert image rectangle coordinates to canvas rectangle coordinates."""
        ix1, iy1, ix2, iy2 = rect_img
        cx1, cy1 = self.image_to_canvas(ix1, iy1)
        cx2, cy2 = self.image_to_canvas(ix2, iy2)
        if cx1 is None or cx2 is None: return None
        return cx1, cy1, cx2, cy2

    def canvas_rect_to_image(self, rect_canvas: Tuple[float, float, float, float]) -> Optional[Tuple[int, int, int, int]]:
        """Convert canvas rectangle coordinates to image rectangle coordinates."""
        cx1, cy1, cx2, cy2 = rect_canvas
        ix1, iy1 = self.canvas_to_image(cx1, cy1)
        ix2, iy2 = self.canvas_to_image(cx2, cy2)
        if ix1 is None or ix2 is None: return None
        iw, ih = self.image_size
        # Clamp image coordinates to image bounds
        ix1 = max(0, min(ix1, iw))
        iy1 = max(0, min(iy1, ih))
        ix2 = max(0, min(ix2, iw))
        iy2 = max(0, min(iy2, ih))
        # Ensure coords are (min_x, min_y, max_x, max_y)
        return int(min(ix1, ix2)), int(min(iy1, iy2)), int(max(ix1, ix2)), int(max(iy1, iy2))

    def get_clamped_image_coords(self, ix: float, iy: float) -> Tuple[int, int]:
        """Get clamped image coordinates within image bounds."""
        iw, ih = self.image_size
        clamped_x = max(0, min(int(ix), iw))
        clamped_y = max(0, min(int(iy), ih))
        return clamped_x, clamped_y

class CropManager:
    """Manages the collection of crops and interactions with the listbox."""
    def __init__(self, canvas: tk.Canvas, coord_converter: CoordinateConverter,
                 listbox: Listbox, on_crops_changed: callable, on_selection_changed: callable):
        self.canvas = canvas
        self.coord_converter = coord_converter
        self.listbox = listbox
        self.on_crops_changed = on_crops_changed # Callback for dirty state, save button state etc.
        self.on_selection_changed = on_selection_changed # Callback for selection dependent UI

        self.crops: Dict[str, Crop] = {} # {crop_id: Crop object}
        self._selected_crop_id: Optional[str] = None
        self._next_order_num = 1

        self.listbox.bind("<<ListboxSelect>>", self._on_listbox_select)
        self.listbox.bind("<Double-Button-1>", lambda e: self.prompt_rename_selected())

    @property
    def selected_crop_id(self) -> Optional[str]:
        return self._selected_crop_id

    @selected_crop_id.setter
    def selected_crop_id(self, cid: Optional[str]):
        if self._selected_crop_id == cid:
            # Only trigger selection changed callback if actually selecting a crop that already is selected
            # (e.g., from canvas click on selected), otherwise let the callback handle it.
            if cid is not None:
                 self.on_selection_changed(cid)
            return

        # Deselect previous
        if self._selected_crop_id and self._selected_crop_id in self.crops:
            prev_crop = self.crops[self._selected_crop_id]
            if prev_crop.rect_id is not None and prev_crop.rect_id in self.canvas.find_withtag(prev_crop.rect_id):
                 self.canvas.itemconfig(prev_crop.rect_id, outline=DEFAULT_RECT_COLOR, width=RECT_WIDTH)

        self._selected_crop_id = cid

        # Select new
        if cid and cid in self.crops:
            crop = self.crops[cid]
            if crop.rect_id is not None and crop.rect_id in self.canvas.find_withtag(crop.rect_id):
                self.canvas.itemconfig(crop.rect_id, outline=SELECTED_RECT_COLOR, width=SELECTED_RECT_WIDTH)
                self.canvas.tag_raise(crop.rect_id)
                # Update listbox selection if necessary (handled by caller for listbox origin)

        self.on_selection_changed(cid)

    def add_crop(self, x1_img: float, y1_img: float, x2_img: float, y2_img: float):
        """Adds a new crop based on image coordinates (can be float)."""
        if self.coord_converter.image_size[0] <= 0: return # No image loaded

        # Clamp and order coordinates
        ix1, iy1, ix2, iy2 = self.coord_converter.canvas_rect_to_image((x1_img, y1_img, x2_img, y2_img))
        # Use floating point for check to allow small movements, then convert to int for storage
        fx1, fy1, fx2, fy2 = min(x1_img, x2_img), min(y1_img, y2_img), max(x1_img, x2_img), max(y1_img, y2_img)

        if (fx2 - fx1) < MIN_CROP_SIZE or (fy2 - fy1) < MIN_CROP_SIZE:
            print(f"Crop too small: {fx2-fx1}x{fy2-fy1}. Min size: {MIN_CROP_SIZE}") # Debugging
            return

        crop_id = str(uuid.uuid4())
        crop_name = f"Crop_{self._next_order_num}"
        coords_int = (ix1, iy1, ix2, iy2)

        new_crop = Crop(id=crop_id, coords=coords_int, name=crop_name, order=self._next_order_num)
        self._next_order_num += 1
        self.crops[crop_id] = new_crop

        # Add to listbox
        self.listbox.insert(tk.END, crop_name)

        # Create canvas rectangle and update crop object
        canvas_coords = self.coord_converter.image_rect_to_canvas(coords_int)
        if canvas_coords:
            rid = self.canvas.create_rectangle(
                *canvas_coords,
                outline=DEFAULT_RECT_COLOR, # Start unselected
                width=RECT_WIDTH,
                tags=(RECT_TAG_PREFIX + crop_id, CROP_RECT_COMMON_TAG)
            )
            new_crop.rect_id = rid

        # Select the new crop
        self.select_crop_by_id(crop_id)
        self.listbox.selection_clear(0, tk.END)
        idx = self._find_listbox_index_by_id(crop_id)
        if idx != -1:
            self.listbox.selection_set(idx)
            self.listbox.activate(idx)
            self.listbox.see(idx)

        self.on_crops_changed() # Signal that crops have been added/changed

    def delete_crop(self, crop_id: str):
        """Deletes a crop by its ID."""
        if crop_id not in self.crops: return

        crop = self.crops[crop_id]
        listbox_name = crop.name # Store before deleting from dict

        # Delete from canvas
        if crop.rect_id is not None and crop.rect_id in self.canvas.find_all():
            self.canvas.delete(crop.rect_id)

        # Delete from listbox
        idx = self._find_listbox_index_by_name(listbox_name)
        if idx != -1:
            self.listbox.delete(idx)

        # Delete from dictionary
        del self.crops[crop_id]

        # Deselect if the deleted crop was selected
        if self.selected_crop_id == crop_id:
            self.selected_crop_id = None # Uses the setter to handle UI updates

        # Auto-select next item in listbox if any
        if self.listbox.size() > 0:
            next_idx = min(idx, self.listbox.size() - 1) if idx != -1 else 0
            self.listbox.selection_set(next_idx)
            self.listbox.activate(next_idx)
            # Trigger listbox select handler to update state/selection
            self._on_listbox_select()
        else:
             # If list is empty, ensure no selection is active
             self.listbox.selection_clear(0, tk.END)
             self.select_crop_by_id(None) # Explicitly deselect if list is empty

        self.on_crops_changed() # Signal change

    def update_crop_coords(self, crop_id: str, new_coords_img: Tuple[float, float, float, float]) -> bool:
        """
        Updates crop coordinates in image pixels (float) and redraws its rectangle.
        Returns True if coords changed, False otherwise.
        Handles clamping to image bounds and minimum size check.
        """
        if crop_id not in self.crops or self.coord_converter.image_size[0] <= 0: return False

        # Clamp and order the proposed image coordinates
        ix1, iy1, ix2, iy2 = self.coord_converter.canvas_rect_to_image(new_coords_img) # Re-use clamping/ordering logic

        # Check min size *after* clamping/ordering
        if (ix2 - ix1) < MIN_CROP_SIZE or (iy2 - iy1) < MIN_CROP_SIZE:
            # Optionally revert to last valid coords or prevent update
            print(f"Proposed update too small: {ix2-ix1}x{iy2-iy1}. Reverting/Preventing.")
            # For simplicity, we just don't update if it becomes too small during drag
            # More complex logic might "stick" at the min size or revert.
            return False

        new_coords_int = (ix1, iy1, ix2, iy2)
        current_coords = self.crops[crop_id].coords

        if new_coords_int != current_coords:
            self.crops[crop_id].coords = new_coords_int
            self.redraw_crop(crop_id)
            self.on_crops_changed() # Signal change
            return True
        return False

    def rename_crop(self, crop_id: str, new_name: str) -> bool:
        """Renames a crop. Returns True if successful, False if name exists."""
        if crop_id not in self.crops: return False
        current_name = self.crops[crop_id].name
        if current_name == new_name: return False # No change

        # Check for duplicates
        for cid, crop in self.crops.items():
            if cid != crop_id and crop.name == new_name:
                return False # Name already exists

        # Update name
        self.crops[crop_id].name = new_name

        # Update listbox
        idx = self._find_listbox_index_by_id(crop_id)
        if idx != -1:
            self.listbox.delete(idx)
            self.listbox.insert(idx, new_name)
            self.listbox.selection_clear(0, tk.END) # Ensure selection is re-applied correctly
            self.listbox.selection_set(idx)
            self.listbox.activate(idx) # Ensure it's visible if needed

        self.on_crops_changed() # Signal change
        return True

    def redraw_all_crops(self):
        """Redraws all crop rectangles on the canvas based on current zoom/pan."""
        if self.coord_converter.image_size[0] <= 0:
             self.canvas.delete(CROP_RECT_COMMON_TAG) # Clear existing if no image
             return

        # Get existing rectangle IDs for cleanup
        existing_rect_ids = set(self.canvas.find_withtag(CROP_RECT_COMMON_TAG))
        updated_or_new_rect_ids = set()

        for crop_id, crop in self.crops.items():
            canvas_coords = self.coord_converter.image_rect_to_canvas(crop.coords)
            if not canvas_coords: continue # Skip if conversion failed

            is_selected = (crop_id == self.selected_crop_id)
            outline_color = SELECTED_RECT_COLOR if is_selected else DEFAULT_RECT_COLOR
            line_width = SELECTED_RECT_WIDTH if is_selected else RECT_WIDTH
            tags = (RECT_TAG_PREFIX + crop_id, CROP_RECT_COMMON_TAG)

            if crop.rect_id is not None and crop.rect_id in self.canvas.find_all(): # Check if ID is still valid on canvas
                # Update existing rectangle
                self.canvas.coords(crop.rect_id, *canvas_coords)
                self.canvas.itemconfig(crop.rect_id, outline=outline_color, width=line_width, tags=tags)
                updated_or_new_rect_ids.add(crop.rect_id)
            else:
                # Create new rectangle
                new_rect_id = self.canvas.create_rectangle(
                    *canvas_coords,
                    outline=outline_color,
                    width=line_width,
                    tags=tags
                )
                crop.rect_id = new_rect_id
                updated_or_new_rect_ids.add(new_rect_id)

        # Delete rectangles that no longer exist in self.crops (cleanup)
        for rect_id in existing_rect_ids - updated_or_new_rect_ids:
             try: self.canvas.delete(rect_id)
             except tk.TclError: pass # Handle cases where the ID might already be gone

        # Ensure selected crop is on top
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            selected_crop = self.crops[self.selected_crop_id]
            if selected_crop.rect_id is not None:
                self.canvas.tag_raise(selected_crop.rect_id)

    def redraw_crop(self, crop_id: str):
         """Redraws a single crop rectangle."""
         if crop_id not in self.crops: return
         crop = self.crops[crop_id]
         if crop.rect_id is None: return # Nothing to redraw yet

         canvas_coords = self.coord_converter.image_rect_to_canvas(crop.coords)
         if not canvas_coords: return

         is_selected = (crop_id == self.selected_crop_id)
         outline_color = SELECTED_RECT_COLOR if is_selected else DEFAULT_RECT_COLOR
         line_width = SELECTED_RECT_WIDTH if is_selected else RECT_WIDTH

         if crop.rect_id in self.canvas.find_all():
             self.canvas.coords(crop.rect_id, *canvas_coords)
             self.canvas.itemconfig(crop.rect_id, outline=outline_color, width=line_width)
             if is_selected: self.canvas.tag_raise(crop.rect_id)

    def select_crop_by_id(self, crop_id: Optional[str], update_listbox=True):
        """Selects a crop by its ID. If None, deselects all."""
        self.selected_crop_id = crop_id # Use setter for UI updates

        if update_listbox:
            self.listbox.selection_clear(0, tk.END)
            if crop_id and crop_id in self.crops:
                idx = self._find_listbox_index_by_id(crop_id)
                if idx != -1:
                    self.listbox.selection_set(idx)
                    self.listbox.activate(idx)
                    self.listbox.see(idx)

    def _on_listbox_select(self, event=None):
        """Handles selection changes in the listbox."""
        selection = self.listbox.curselection()
        if selection:
            selected_index = selection[0]
            selected_name = self.listbox.get(selected_index)
            # Find crop ID by name (efficient enough for typical number of crops)
            selected_crop_id = None
            for cid, crop in self.crops.items():
                if crop.name == selected_name:
                    selected_crop_id = cid
                    break
            self.select_crop_by_id(selected_crop_id, update_listbox=False) # Avoid recursion
        else:
            self.select_crop_by_id(None, update_listbox=False)

    def prompt_rename_selected(self):
        """Prompts user to rename the currently selected crop."""
        if not self.selected_crop_id or self.selected_crop_id not in self.crops:
            messagebox.showwarning("Rename Error", "Please select a crop to rename.", parent=self.canvas.winfo_toplevel())
            return

        crop_to_rename = self.crops[self.selected_crop_id]
        current_name = crop_to_rename.name

        dialog = ctk.CTkInputDialog(
            text=f"New name for '{current_name}':",
            title="Rename Crop",
            entry_fg_color="white", # Standard CTk colors are fine
            entry_text_color="black"
        )
        # Position dialog near the window center
        main_window = self.canvas.winfo_toplevel()
        dialog.geometry(f"+{main_window.winfo_x()+200}+{main_window.winfo_y()+200}")

        new_name_raw = dialog.get_input()

        if new_name_raw is None or not new_name_raw.strip():
            # User cancelled or entered empty name
            # Add a status update callback here maybe?
            return

        new_name = new_name_raw.strip()

        if not self.rename_crop(self.selected_crop_id, new_name):
            messagebox.showerror("Rename Error", f"Name '{new_name}' already exists or is invalid.", parent=main_window)

    def clear_all_crops(self):
        """Clears all crops from memory and canvas."""
        self.canvas.delete(CROP_RECT_COMMON_TAG)
        self.crops.clear()
        self.listbox.delete(0, tk.END)
        self.selected_crop_id = None # Uses setter
        self._next_order_num = 1
        self.on_crops_changed() # Signal change

    def _find_listbox_index_by_id(self, crop_id: str) -> int:
        """Finds the listbox index for a given crop ID."""
        if crop_id not in self.crops: return -1
        target_name = self.crops[crop_id].name
        return self._find_listbox_index_by_name(target_name)

    def _find_listbox_index_by_name(self, name: str) -> int:
        """Finds the listbox index for a given crop name."""
        for i in range(self.listbox.size()):
            if self.listbox.get(i) == name:
                return i
        return -1

    def get_crop_by_canvas_id(self, canvas_id: int) -> Optional[Crop]:
        """Finds a Crop object given its canvas rectangle ID."""
        tags = self.canvas.gettags(canvas_id)
        for tag in tags:
            if tag.startswith(RECT_TAG_PREFIX):
                crop_id = tag[len(RECT_TAG_PREFIX):]
                if crop_id in self.crops:
                    return self.crops[crop_id]
        return None

    def get_selected_crop(self) -> Optional[Crop]:
        """Returns the currently selected Crop object."""
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            return self.crops[self.selected_crop_id]
        return None

    def nudge_selected_crop(self, dx_img: int, dy_img: int):
        """Nudges the selected crop by the given delta in image pixels."""
        crop = self.get_selected_crop()
        if crop:
            x1, y1, x2, y2 = crop.coords
            new_coords_img = (x1 + dx_img, y1 + dy_img, x2 + dx_img, y2 + dy_img)
            if self.update_crop_coords(crop.id, new_coords_img):
                return True # Coords updated
        return False

    def resize_selected_crop_key(self, dx_img: int, dy_img: int, handle_dir: str):
        """Resizes the selected crop based on arrow key input."""
        crop = self.get_selected_crop()
        if crop:
            x1, y1, x2, y2 = crop.coords
            nx1, ny1, nx2, ny2 = x1, y1, x2, y2

            # Apply deltas based on handle direction
            if 'n' in handle_dir: ny1 += dy_img # dy_img will be negative for Up
            if 's' in handle_dir: ny2 += dy_img # dy_img will be positive for Down
            if 'w' in handle_dir: nx1 += dx_img # dx_img will be negative for Left
            if 'e' in handle_dir: nx2 += dx_img # dx_img will be positive for Right

            # Create the new coordinate tuple, ensuring min/max order for update_crop_coords
            new_coords_img = (nx1, ny1, nx2, ny2) # update_crop_coords handles min/max ordering and clamping

            if self.update_crop_coords(crop.id, new_coords_img):
                return True # Coords updated
        return False

class CanvasHandler:
    """Handles mouse interactions on the canvas (drawing, moving, resizing, pan, zoom)."""
    def __init__(self, canvas: tk.Canvas, coord_converter: CoordinateConverter, crop_manager: CropManager,
                 on_status_update: callable, on_cursor_update: callable):
        self.canvas = canvas
        self.coord_converter = coord_converter
        self.crop_manager = crop_manager
        self.on_status_update = on_status_update # Callback for status bar
        self.on_cursor_update = on_cursor_update # Callback for cursor changes

        # Drawing State
        self._is_drawing = False
        self._start_canvas_x: Optional[float] = None
        self._start_canvas_y: Optional[float] = None
        self._current_temp_rect_id: Optional[int] = None

        # Moving State
        self._is_moving = False
        self._move_offset_x: float = 0.0 # Canvas x offset from mouse to rect corner
        self._move_offset_y: float = 0.0 # Canvas y offset from mouse to rect corner
        self._start_coords_img: Optional[Tuple[int, int, int, int]] = None # Original image coords when drag started

        # Resizing State
        self._is_resizing = False
        self._resize_handle: Optional[str] = None # e.g., 'nw', 'se', 'n', 's'
        self._start_canvas_x_resize: Optional[float] = None # Canvas x when resize started
        self._start_canvas_y_resize: Optional[float] = None # Canvas y when resize started
        self._start_coords_img_resize: Optional[Tuple[int, int, int, int]] = None # Original image coords when resize started

        # Pan State
        self._is_panning = False
        self._pan_start_x: float = 0.0 # Canvas x when pan started
        self._pan_start_y: float = 0.0 # Canvas y when pan started

        self._bind_events()

    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_press_left)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag_left)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_release_left)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel) # Windows/macOS
        self.canvas.bind("<ButtonPress-4>", lambda e: self._on_mouse_wheel(e, 1)) # Linux scroll up
        self.canvas.bind("<ButtonPress-5>", lambda e: self._on_mouse_wheel(e, -1)) # Linux scroll down
        self.canvas.bind("<ButtonPress-2>", self._on_pan_press) # Middle button
        self.canvas.bind("<B2-Motion>", self._on_pan_drag)
        self.canvas.bind("<ButtonRelease-2>", self._on_pan_release)
        self.canvas.bind("<Motion>", self._on_mouse_motion)
        self.canvas.bind("<Enter>", self._on_mouse_motion) # To update cursor on enter
        self.canvas.bind("<Leave>", self._on_mouse_leave)

    def _on_mouse_press_left(self, event):
        self.canvas.focus_set() # Allow keyboard shortcuts
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        # 1. Check for resize handle click
        handle = self._get_resize_handle_at(cx, cy)
        if handle and self.crop_manager.selected_crop_id:
            self._is_resizing = True
            self._resize_handle = handle
            self._start_canvas_x_resize, self._start_canvas_y_resize = cx, cy
            # Store original image coords at the start of resize
            selected_crop = self.crop_manager.get_selected_crop()
            if selected_crop:
                 self._start_coords_img_resize = selected_crop.coords
                 self.on_status_update(action_text=f"Resizing ({handle})")
                 self.on_cursor_update(f"size_{handle}") # Set specific resize cursor
            return

        # 2. Check for crop click (to select or move)
        clicked_canvas_item = self.canvas.find_overlapping(cx-1, cy-1, cx+1, cy+1)
        clicked_crop_id = None
        # Iterate backwards to prioritize items on top (more recently drawn or raised)
        for item_id in reversed(clicked_canvas_item):
            tags = self.canvas.gettags(item_id)
            if CROP_RECT_COMMON_TAG in tags and tags[0].startswith(RECT_TAG_PREFIX):
                cid = tags[0][len(RECT_TAG_PREFIX):]
                if cid in self.crop_manager.crops: # Ensure it's a valid crop ID
                    clicked_crop_id = cid
                    break # Found the topmost crop rectangle

        if clicked_crop_id:
            # Select the clicked crop
            self.crop_manager.select_crop_by_id(clicked_crop_id)
            # Start moving it
            self._is_moving = True
            rect_coords = self.canvas.coords(self.crop_manager.crops[clicked_crop_id].rect_id)
            self._move_offset_x, self._move_offset_y = cx - rect_coords[0], cy - rect_coords[1]
             # Store original image coords at the start of move
            selected_crop = self.crop_manager.get_selected_crop()
            if selected_crop:
                 self._start_coords_img = selected_crop.coords
                 self.on_status_update(action_text="Moving Crop")
                 self.on_cursor_update("fleur")
            return

        # 3. If no handle or crop was clicked, start drawing
        if self.coord_converter.image_size[0] > 0: # Only draw if an image is loaded
            self._is_drawing = True
            self._start_canvas_x, self._start_canvas_y = cx, cy
            # Deselect any current crop before drawing a new one
            self.crop_manager.select_crop_by_id(None)
            # Create a temporary rectangle for visual feedback
            self._current_temp_rect_id = self.canvas.create_rectangle(
                cx, cy, cx, cy,
                outline=SELECTED_RECT_COLOR,
                width=RECT_WIDTH,
                dash=(4, 4),
                tags=(TEMP_RECT_TAG,)
            )
            self.on_status_update(action_text="Drawing Crop")
            self.on_cursor_update("crosshair")


    def _on_mouse_drag_left(self, event):
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self._is_drawing and self._current_temp_rect_id:
            self.canvas.coords(self._current_temp_rect_id, self._start_canvas_x, self._start_canvas_y, cx, cy)
        elif self._is_moving and self.crop_manager.selected_crop_id and self._start_coords_img:
            selected_crop = self.crop_manager.get_selected_crop()
            if selected_crop:
                # Calculate intended canvas coordinates based on mouse position and initial offset
                intended_cx1 = cx - self._move_offset_x
                intended_cy1 = cy - self._move_offset_y

                # Get dimensions of the crop from the *current* canvas rectangle
                rect_coords = self.canvas.coords(selected_crop.rect_id)
                width_c, height_c = rect_coords[2] - rect_coords[0], rect_coords[3] - rect_coords[1]

                # Calculate the *intended* canvas bottom-right corner
                intended_cx2 = intended_cx1 + width_c
                intended_cy2 = intended_cy1 + height_c

                # Convert intended canvas coordinates to image coordinates
                # The update_crop_coords method will handle clamping to image bounds
                self.crop_manager.update_crop_coords(selected_crop.id, (intended_cx1, intended_cy1, intended_cx2, intended_cy2))

        elif self._is_resizing and self.crop_manager.selected_crop_id and self._resize_handle and self._start_coords_img_resize:
             selected_crop = self.crop_manager.get_selected_crop()
             if selected_crop:
                # Get original image coords from drag start
                oxi1, oyi1, oxi2, oyi2 = self._start_coords_img_resize

                # Calculate delta in image coordinates based on canvas mouse movement
                current_img_x, current_img_y = self.coord_converter.canvas_to_image(cx, cy)
                start_img_x, start_img_y = self.coord_converter.canvas_to_image(self._start_canvas_x_resize, self._start_canvas_y_resize)

                if current_img_x is None or start_img_x is None: return # Conversion failed

                dxi = current_img_x - start_img_x
                dyi = current_img_y - start_img_y

                # Calculate new image coordinates based on the resize handle
                nx1, ny1, nx2, ny2 = oxi1, oyi1, oxi2, oyi2

                if 'n' in self._resize_handle: ny1 += dyi
                if 's' in self._resize_handle: ny2 += dyi
                if 'w' in self._resize_handle: nx1 += dxi
                if 'e' in self._resize_handle: nx2 += dxi

                # Update crop coordinates (will handle clamping and min size check)
                self.crop_manager.update_crop_coords(selected_crop.id, (nx1, ny1, nx2, ny2))

        self._on_mouse_motion(event) # Update cursor/coords during drag


    def _on_mouse_release_left(self, event):
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self._is_drawing and self._start_canvas_x is not None and self._start_canvas_y is not None:
            # Clean up temporary rectangle
            if self._current_temp_rect_id in self.canvas.find_withtag(TEMP_RECT_TAG):
                 self.canvas.delete(self._current_temp_rect_id)
            self._current_temp_rect_id = None

            # Add the new crop if it's large enough
            img_x1, img_y1 = self.coord_converter.canvas_to_image(self._start_canvas_x, self._start_canvas_y)
            img_x2, img_y2 = self.coord_converter.canvas_to_image(cx, cy)

            if img_x1 is not None and img_y1 is not None and img_x2 is not None and img_y2 is not None:
                 self.crop_manager.add_crop(img_x1, img_y1, img_x2, img_y2) # Handles min size check internally
            else:
                 self.on_status_update(action_text="Failed to add crop (coord error)")


        # Reset state variables
        self._is_drawing = False
        self._is_moving = False
        self._is_resizing = False
        self._start_canvas_x = None
        self._start_canvas_y = None
        self._start_canvas_x_resize = None
        self._start_canvas_y_resize = None
        self._resize_handle = None
        self._start_coords_img = None
        self._start_coords_img_resize = None

        self._on_mouse_motion(event) # Update cursor to idle state
        self.on_status_update(action_text="Ready")


    def _on_mouse_wheel(self, event, direction=None):
        if self.coord_converter.image_size[0] <= 0: return # No image loaded

        # Determine scroll direction
        delta = 0
        if direction:
            delta = direction # For Linux buttons 4, 5
        elif event.num == 5 or event.delta < 0:
            delta = -1 # Scroll down
        elif event.num == 4 or event.delta > 0:
            delta = 1 # Scroll up
        else:
            return # Unknown scroll event

        zoom_increment_factor = 1.1 # Zoom 10% in/out
        min_zoom, max_zoom = 0.01, 25.0 # Define zoom limits

        # Get mouse position in canvas and image coordinates *before* changing zoom
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        img_x_before, img_y_before = self.coord_converter.canvas_to_image(cx, cy)

        if img_x_before is None: return # Cannot perform zoom around a point if coord conversion fails

        # Calculate new zoom factor
        new_zoom_factor = self.coord_converter.zoom_factor * zoom_increment_factor if delta > 0 else self.coord_converter.zoom_factor / zoom_increment_factor
        new_zoom_factor = max(min_zoom, min(max_zoom, new_zoom_factor))

        # Prevent tiny changes
        if abs(new_zoom_factor - self.coord_converter.zoom_factor) < 0.001:
            return

        # Calculate new canvas offset to keep the point under the cursor stable
        # canvas_x = (image_x * zoom) + offset_x
        # offset_x = canvas_x - (image_x * zoom)
        new_offset_x = cx - (img_x_before * new_zoom_factor)
        new_offset_y = cy - (img_y_before * new_zoom_factor)

        # Update coordinate converter
        self.coord_converter.set_zoom_pan(new_zoom_factor, new_offset_x, new_offset_y)

        # Redraw image and all crops with new zoom/pan
        self._redraw_canvas_content()

        self.on_status_update(
            action_text=f"Zoom {'In' if delta > 0 else 'Out'}",
            zoom_text=f"Zoom: {self.coord_converter.zoom_factor:.1%}"
        )


    def _on_pan_press(self, event):
        if self.coord_converter.image_size[0] <= 0: return # No image loaded
        self._is_panning = True
        # Get start position in canvas coordinates
        self._pan_start_x, self._pan_start_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.on_cursor_update("fleur") # Change cursor to indicate panning
        self.on_status_update(action_text="Panning")

    def _on_pan_drag(self, event):
        if not self._is_panning or self.coord_converter.image_size[0] <= 0: return

        # Get current position in canvas coordinates
        current_cx, current_cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        # Calculate displacement
        dx = current_cx - self._pan_start_x
        dy = current_cy - self._pan_start_y

        # Update canvas offset
        new_offset_x = self.coord_converter.canvas_offset_x + dx
        new_offset_y = self.coord_converter.canvas_offset_y + dy
        self.coord_converter.set_zoom_pan(self.coord_converter.zoom_factor, new_offset_x, new_offset_y)

        # Move all items on the canvas
        self.canvas.move("all", dx, dy)

        # Update start position for the next drag event
        self._pan_start_x, self._pan_start_y = current_cx, current_cy


    def _on_pan_release(self, event):
        self._is_panning = False
        self._on_mouse_motion(event) # Update cursor to hover state
        self.on_status_update(action_text="Ready")

    def _on_mouse_motion(self, event):
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        # Update status bar coordinates
        img_x, img_y = self.coord_converter.canvas_to_image(cx, cy)
        coords_text = " Img Coords: --- "
        if img_x is not None and img_y is not None:
             clamped_x, clamped_y = self.coord_converter.get_clamped_image_coords(img_x, img_y)
             coords_text = f" Img Coords: {clamped_x:>4}, {clamped_y:>4}"
        self.on_status_update(coords_text=coords_text)

        # Update cursor based on state (drawing, moving, resizing) or hover
        if self._is_panning: self.on_cursor_update("fleur")
        elif self._is_moving: self.on_cursor_update("fleur") # Moving uses fleur
        elif self._is_resizing:
            # Cursor was set on press, keep it during drag
            pass # Cursor is already set by _on_mouse_press_left
        elif self._is_drawing: self.on_cursor_update("crosshair")
        else: # Idle state, check hover
            handle = self._get_resize_handle_at(cx, cy)
            if handle:
                self.on_cursor_update(f"size_{handle}")
            else:
                 # Check if hovering inside the selected crop
                 selected_crop = self.crop_manager.get_selected_crop()
                 if selected_crop and selected_crop.rect_id is not None:
                     rect_coords = self.canvas.coords(selected_crop.rect_id)
                     if len(rect_coords) == 4: # Ensure coords exist
                         c1, r1, c2, r2 = rect_coords
                         # Check if mouse is inside the rectangle (with a small margin)
                         margin = 1 # Pixels inside the border
                         if (c1 + margin) < cx < (c2 - margin) and (r1 + margin) < cy < (r2 - margin):
                             self.on_cursor_update("fleur") # Indicate can move
                             return # Handled hover inside
                 # Default cursor if not drawing/moving/resizing and not hovering handle/selected crop
                 self.on_cursor_update("") # "" means default cursor


    def _on_mouse_leave(self, event):
        self.on_status_update(coords_text=" Img Coords: --- ")
        if not (self._is_drawing or self._is_moving or self._is_resizing or self._is_panning):
             self.on_cursor_update("") # Reset cursor

    def _get_resize_handle_at(self, cx: float, cy: float) -> Optional[str]:
        """Check if mouse is over a resize handle of the selected crop."""
        crop = self.crop_manager.get_selected_crop()
        if not crop or crop.rect_id is None: return None

        rect_coords = self.canvas.coords(crop.rect_id)
        if not rect_coords or len(rect_coords) != 4: return None

        c1, r1, c2, r2 = rect_coords # Canvas coordinates of the crop rectangle
        m = HANDLE_SIZE / 2.0 # Half of the handle size as margin

        # Check corners
        if abs(cx - c1) < m and abs(cy - r1) < m: return 'nw'
        if abs(cx - c2) < m and abs(cy - r1) < m: return 'ne'
        if abs(cx - c1) < m and abs(cy - r2) < m: return 'sw'
        if abs(cx - c2) < m and abs(cy - r2) < m: return 'se'

        # Check sides (within the bounds of the side)
        ib = m # Small margin inside the handle area to prevent handle overlaps
        if abs(cy - r1) < m and (c1 + ib) < cx < (c2 - ib): return 'n'
        if abs(cy - r2) < m and (c1 + ib) < cx < (c2 - ib): return 's'
        if abs(cx - c1) < m and (r1 + ib) < cy < (r2 - ib): return 'w'
        if abs(cx - c2) < m and (r1 + ib) < cy < (r2 - ib): return 'e'

        return None

    def _redraw_canvas_content(self):
        """Redraws the image and all crops on the canvas."""
        canvas_w, canvas_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        # Use requested size if not yet mapped or size is zero
        if canvas_w <= 1: canvas_w = self.canvas.winfo_reqwidth()
        if canvas_h <= 1: canvas_h = self.canvas.winfo_reqheight()

        if self.coord_converter.image_size[0] <= 0:
             self.canvas.delete("all")
             self.on_status_update(action_text="Ready (No image)")
             return

        img_w, img_h = self.coord_converter.image_size
        display_w = max(1, int(img_w * self.coord_converter.zoom_factor))
        display_h = max(1, int(img_h * self.coord_converter.zoom_factor))

        try:
            # Get the original image from the main app (need a reference or pass it)
            # For simplicity here, let's assume the main app holds the original image
            # and we need a callback or direct access to it.
            # A better design might pass the display image generation responsiblity
            # to the main app or a separate image handler.
            # Let's add a get_original_image callback/method to the main app
            original_image = self.canvas.winfo_toplevel().get_original_image()
            if original_image is None: raise ValueError("Original image not available")

            display_image = original_image.resize((display_w, display_h), Image.Resampling.LANCZOS)
            self.canvas.tk_image = ImageTk.PhotoImage(display_image) # Keep a reference!
        except Exception as e:
            print(f"Error resizing image for display: {e}")
            self.canvas.delete("all")
            self.on_status_update(action_text="Display Error")
            self.canvas.tk_image = None # Clear reference on error
            return

        # Clear existing content (except temporary items if drawing)
        # Delete image tag and all crop rectangles
        self.canvas.delete(IMAGE_TAG)
        self.canvas.delete(CROP_RECT_COMMON_TAG)

        # Draw the new image
        img_x0 = int(round(self.coord_converter.canvas_offset_x))
        img_y0 = int(round(self.coord_converter.canvas_offset_y))
        self.canvas.create_image(img_x0, img_y0, anchor=tk.NW, image=self.canvas.tk_image, tags=IMAGE_TAG)

        # Redraw all crop rectangles
        self.crop_manager.redraw_all_crops()


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

        # Apply DPI awareness for Windows
        try: from ctypes import windll; windll.shcore.SetProcessDpiAwareness(1)
        except: pass

        # --- State Variables ---
        self.image_path: Optional[str] = None
        self._original_image: Optional[Image.Image] = None # PIL Image object
        self.tk_image: Optional[ImageTk.PhotoImage] = None # Tkinter PhotoImage reference

        self.current_save_dir: Optional[str] = None # Stores the target dir for the current image session
        self._is_dirty = False # Track unsaved changes

        # --- Core Components ---
        self.coord_converter = CoordinateConverter()
        self.crop_manager: Optional[CropManager] = None # Initialized after canvas creation
        self.canvas_handler: Optional[CanvasHandler] = None # Initialized after canvas creation

        # --- UI Layout ---
        self._setup_ui()

        # --- Bindings ---
        self._bind_global_events()

        # Initial status bar update
        self._update_status_bar()

    def _setup_ui(self):
        """Sets up the main application UI layout and widgets."""
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

        # Use raw tk.Canvas for performance/compatibility with PIL PhotoImage
        self.canvas = tk.Canvas(self.image_frame, bg="gray90", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # --- Right Frame (Controls) ---
        self.control_frame = ctk.CTkFrame(self.main_frame, width=280)
        self.control_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False) # Prevent frame from resizing based on contents
        self.control_frame.grid_columnconfigure(0, weight=1)
        self.control_frame.grid_columnconfigure(1, weight=1)
        self.control_frame.grid_rowconfigure(3, weight=1) # Listbox row grows

        # Control Buttons
        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image (Ctrl+O)", command=self._handle_open)
        self.btn_select_image.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="ew")

        self.btn_save = ctk.CTkButton(self.control_frame, text="Save (Ctrl+S)", command=self._handle_save, state=tk.DISABLED)
        self.btn_save.grid(row=1, column=0, padx=(10, 5), pady=5, sticky="ew")

        self.btn_save_as = ctk.CTkButton(self.control_frame, text="Save As...", command=self._handle_save_as, state=tk.DISABLED)
        self.btn_save_as.grid(row=1, column=1, padx=(5, 10), pady=5, sticky="ew")

        # Crop List Area
        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List (Double-click to rename):")
        self.lbl_crop_list.grid(row=2, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="w")

        # Using standard Listbox for better performance with many items
        self.crop_listbox = Listbox(self.control_frame, bg='white', fg='black',
                                    selectbackground='#CDEAFE', selectforeground='black',
                                    highlightthickness=1, highlightbackground="#CCCCCC",
                                    highlightcolor="#89C4F4", borderwidth=0, exportselection=False)
        self.crop_listbox.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")


        # Rename/Delete Buttons
        self.btn_rename_crop = ctk.CTkButton(self.control_frame, text="Rename", command=lambda: self.crop_manager.prompt_rename_selected() if self.crop_manager else None, state=tk.DISABLED)
        self.btn_rename_crop.grid(row=4, column=0, padx=(10, 5), pady=(5, 10), sticky="sew")

        self.btn_delete_crop = ctk.CTkButton(self.control_frame, text="Delete (Del)", command=self._delete_selected_crop, state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F")
        self.btn_delete_crop.grid(row=4, column=1, padx=(5, 10), pady=(5, 10), sticky="sew")

        # --- Status Bar ---
        self.status_bar = ctk.CTkFrame(self, height=25, fg_color="gray85")
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=0, pady=(0,0))
        self.status_bar.grid_columnconfigure(0, weight=1); self.status_bar.grid_columnconfigure(1, weight=1); self.status_bar.grid_columnconfigure(2, weight=1)

        self.lbl_status_coords = ctk.CTkLabel(self.status_bar, text=" Img Coords: --- ", text_color="gray30", height=20, anchor="w")
        self.lbl_status_coords.grid(row=0, column=0, sticky="w", padx=(10, 0))
        self.lbl_status_action = ctk.CTkLabel(self.status_bar, text="Ready", text_color="gray30", height=20, anchor="center")
        self.lbl_status_action.grid(row=0, column=1, sticky="ew")
        self.lbl_status_zoom_select = ctk.CTkLabel(self.status_bar, text="Zoom: 100.0% | Sel: --- ", text_color="gray30", height=20, anchor="e")
        self.lbl_status_zoom_select.grid(row=0, column=2, sticky="e", padx=(0, 10))

        # Initialize CropManager and CanvasHandler *after* canvas is created
        self.crop_manager = CropManager(
            canvas=self.canvas,
            coord_converter=self.coord_converter,
            listbox=self.crop_listbox,
            on_crops_changed=self._on_crops_changed,
            on_selection_changed=self._on_selection_changed
        )
        self.canvas_handler = CanvasHandler(
            canvas=self.canvas,
            coord_converter=self.coord_converter,
            crop_manager=self.crop_manager,
            on_status_update=self._update_status_bar,
            on_cursor_update=self._update_canvas_cursor
        )

    def _bind_global_events(self):
        """Binds application-wide keyboard shortcuts and window events."""
        self.bind_all("<Control-o>", self._handle_open_event)
        self.bind_all("<Control-O>", self._handle_open_event)
        self.bind_all("<Control-s>", self._handle_save_event)
        self.bind_all("<Control-S>", self._handle_save_event)
        self.bind_all("<Delete>", self._handle_delete_event) # Corrected name

        # Nudge/Resize Bindings - Delegate to CropManager via handler for now
        # Could delegate directly if CropManager handles coords only
        # Let's have the app handle these, calling CropManager
        self.bind_all("<Left>", lambda e: self._handle_nudge(-1, 0))
        self.bind_all("<Right>", lambda e: self._handle_nudge(1, 0))
        self.bind_all("<Up>", lambda e: self._handle_nudge(0, -1))
        self.bind_all("<Down>", lambda e: self._handle_nudge(0, 1))
        self.bind_all("<Shift-Left>", lambda e: self._handle_resize_key(-1, 0, 'w'))
        self.bind_all("<Shift-Right>", lambda e: self._handle_resize_key(1, 0, 'e'))
        self.bind_all("<Shift-Up>", lambda e: self._handle_resize_key(0, -1, 'n'))
        self.bind_all("<Shift-Down>", lambda e: self._handle_resize_key(0, 1, 's'))


        # Window Events
        self.bind("<Configure>", self._on_window_resize)
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    # --- Image Handling ---
    def _handle_open_event(self, event=None): self._handle_open(); return "break"
    def _handle_open(self):
        """Prompts user to select an image file and loads it."""
        if not self._check_unsaved_changes(): return

        path = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp"),
                ("All files", "*.*")
            ],
            parent=self
        )
        if not path:
            self._update_status_bar(action_text="Image Selection Cancelled")
            return

        self._update_status_bar(action_text="Loading..."); self.update_idletasks()

        try:
            img = Image.open(path)
            # Convert image to modes compatible with Tkinter/saving
            if img.mode == 'CMYK': img = img.convert('RGB')
            elif img.mode == 'P': img = img.convert('RGBA') # Preserve transparency if possible, handle saving later
            elif img.mode == 'LA': img = img.convert('RGBA') # Preserve transparency if possible

            self.image_path = path
            self._original_image = img

            # Calculate initial zoom and pan to fit image
            canvas_w, canvas_h = self.canvas.winfo_width(), self.canvas.winfo_height()
            # Use requested size if window isn't fully configured yet
            if canvas_w <= 1: canvas_w = self.canvas.winfo_reqwidth()
            if canvas_h <= 1: canvas_h = self.canvas.winfo_reqheight()

            img_w, img_h = self._original_image.size
            if img_w <= 0 or img_h <= 0: raise ValueError("Invalid image dimensions")

            # Calculate zoom factor to fit within canvas bounds, leaving a small margin
            padding_factor = 0.98
            zoom_w = (canvas_w / img_w) if img_w > 0 else 1.0
            zoom_h = (canvas_h / img_h) if img_h > 0 else 1.0
            initial_zoom = min(zoom_w, zoom_h, 1.0) * padding_factor # Don't zoom in beyond 100% initially

            display_w = img_w * initial_zoom
            display_h = img_h * initial_zoom

            # Calculate initial pan offset to center the image
            offset_x = (canvas_w - display_w) / 2.0
            offset_y = (canvas_h - display_h) / 2.0

            # Update components
            self.coord_converter.set_image_data(img_w, img_h)
            self.coord_converter.set_zoom_pan(initial_zoom, offset_x, offset_y)
            self.crop_manager.clear_all_crops() # Clear previous crops
            self.current_save_dir = None # Reset save directory

            # Display the image and redraw crops
            self.canvas_handler._redraw_canvas_content() # Access private method for internal refresh

            # Update UI element states
            self.btn_save.configure(state=tk.DISABLED) # Enable only after crops are added
            self.btn_save_as.configure(state=tk.DISABLED) # Enable only after crops are added
            self.set_dirty(False) # Mark as clean initially

            self._update_status_bar(
                action_text="Image Loaded",
                zoom_text=f"Zoom: {self.coord_converter.zoom_factor:.1%}"
            )

        except FileNotFoundError:
            messagebox.showerror("Error", f"File not found:\n{path}", parent=self)
            self._reset_app_state()
            self._update_status_bar(action_text="Error: File Not Found")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open or process image:\n{e}", parent=self)
            self._reset_app_state()
            self._update_status_bar(action_text="Error Loading Image")

    def _reset_app_state(self):
        """Resets the application state when image loading fails or image is cleared."""
        self.image_path = None
        self._original_image = None
        self.tk_image = None
        self.current_save_dir = None
        self.set_dirty(False)
        self.coord_converter.set_image_data(0, 0) # Reset converter
        self.coord_converter.set_zoom_pan(1.0, 0.0, 0.0) # Reset converter
        if self.crop_manager: self.crop_manager.clear_all_crops() # Clear crops via manager
        self.canvas.delete("all") # Clear canvas
        self.btn_save.configure(state=tk.DISABLED)
        self.btn_save_as.configure(state=tk.DISABLED)
        self._update_status_bar() # Reset status bar


    def get_original_image(self) -> Optional[Image.Image]:
        """Allows CanvasHandler to access the original image."""
        return self._original_image

    # --- Save Handling ---
    def _handle_save_event(self, event=None): self._handle_save(); return "break"

    def _handle_save(self):
        """Saves crops to the last used or default directory."""
        if not self._check_save_preconditions(): return

        target_dir = self.current_save_dir

        if not target_dir:
            # Determine default save directory (subfolder next to image)
            try:
                if not self.image_path: raise ValueError("Image path not set")
                img_dir = os.path.dirname(self.image_path)
                base_name = os.path.splitext(os.path.basename(self.image_path))[0]
                if not base_name: raise ValueError("Could not determine base name from image path")
                target_dir = os.path.join(img_dir, base_name)

                # Create directory if it doesn't exist
                os.makedirs(target_dir, exist_ok=True)
                self.current_save_dir = target_dir # Store for future saves
            except Exception as e:
                messagebox.showerror("Directory Error", f"Could not determine/create default save directory:\n{e}", parent=self)
                self._update_status_bar(action_text="Save Failed (Dir Error)")
                return

        # Perform the save operation with sequential naming
        self._perform_save(target_dir=target_dir, use_sequential_naming=True)

    def _handle_save_as(self):
        """Prompts user for a directory and saves crops using their names."""
        if not self._check_save_preconditions(): return

        # Determine initial directory for the dialog
        initial_dir = self.current_save_dir
        if not initial_dir and self.image_path:
            try:
                # Suggest a subfolder next to the image as a starting point
                img_dir = os.path.dirname(self.image_path)
                base_name = os.path.splitext(os.path.basename(self.image_path))[0]
                if base_name: initial_dir = os.path.join(img_dir, base_name)
            except: pass # Ignore errors, filedialog will default

        output_dir = filedialog.askdirectory(
            parent=self,
            title="Select Folder to Save Cropped Images",
            initialdir=initial_dir
        )

        if not output_dir:
            self._update_status_bar(action_text="Save As Cancelled")
            return

        self.current_save_dir = output_dir # Store for future "Save" clicks

        # Perform the save operation using crop names
        self._perform_save(target_dir=output_dir, use_sequential_naming=False)

    def _check_save_preconditions(self) -> bool:
        """Checks if saving is possible (image loaded, crops exist)."""
        if self._original_image is None or not self.image_path:
            messagebox.showwarning("Save Error", "No image loaded.", parent=self)
            return False
        if not self.crop_manager or not self.crop_manager.crops:
            messagebox.showwarning("Save Error", "No crops defined.", parent=self)
            return False
        return True

    def _perform_save(self, target_dir: str, use_sequential_naming: bool):
        """Core logic for saving crops to a specified directory."""
        self._update_status_bar(action_text="Saving..."); self.update_idletasks() # Update UI immediately

        saved_count, error_count = 0, 0
        error_messages = []

        # Sort crops by their original order number for sequential naming compatibility
        # Even when using names, saving in original order might be preferred
        sorted_crops_items = sorted(self.crop_manager.crops.items(), key=lambda item: item[1].order)

        base_img_name = ""
        if self.image_path:
            base_img_name = os.path.splitext(os.path.basename(self.image_path))[0]

        for i, (crop_id, crop) in enumerate(sorted_crops_items):
            coords = crop.coords
            crop_name = crop.name

            if not coords or len(coords) != 4:
                error_count += 1
                error_messages.append(f"Skip '{crop_name}': Invalid coordinates")
                continue

            # Determine filename
            if use_sequential_naming:
                # Use the index in the sorted list (0-based) + 1
                filename = f"{base_img_name}_{i + 1}.jpg"
            else:
                # Sanitize crop name for use in filename
                sanitized_name = re.sub(r'[\\/*?:"<>|]', '_', crop_name).strip()
                # Ensure filename is not empty after sanitizing, use order number if needed
                if not sanitized_name:
                    sanitized_name = f"Crop_{crop.order}" # Fallback to order number
                filename = f"{sanitized_name}.jpg"

            file_path = os.path.join(target_dir, filename)
            image_crop_coords = tuple(map(int, coords)) # Ensure integer coordinates for PIL

            try:
                # Use the original image for cropping
                cropped_image = self._original_image.crop(image_crop_coords)

                # Convert image to RGB if needed for JPEG save
                # Handle transparency: blend with white background for JPEG
                if cropped_image.mode in ('RGBA', 'P', 'LA'):
                    background = Image.new("RGB", cropped_image.size, (255, 255, 255))
                    # Use the alpha channel as mask if available
                    alpha_mask = cropped_image.split()[-1] if 'A' in cropped_image.mode else None
                    background.paste(cropped_image, mask=alpha_mask)
                    cropped_image = background
                elif cropped_image.mode != 'RGB':
                     cropped_image = cropped_image.convert('RGB')

                cropped_image.save(file_path, "JPEG", quality=95, optimize=True)
                saved_count += 1

            except Exception as e:
                error_count += 1
                error_msg = f"Error saving '{filename}': {e}"
                print(error_msg) # Log error
                error_messages.append(error_msg)

        if error_count == 0:
            self.set_dirty(False) # Mark as clean if all saved successfully
            messagebox.showinfo("Save Successful", f"Successfully saved {saved_count} crops to:\n{target_dir}", parent=self)
            self._update_status_bar(action_text="Saved OK")
        else:
            # Truncate error messages for the dialog box
            error_summary = "\n - ".join(error_messages[:5])
            if len(error_messages) > 5:
                error_summary += "\n - (...more errors not shown)"
            messagebox.showwarning(
                "Save Completed with Errors",
                f"Saved {saved_count} crops. Failed to save {error_count} crops to:\n{target_dir}\n\nErrors:\n - {error_summary}",
                parent=self
            )
            self._update_status_bar(action_text="Saved (with errors)")


    # --- Unsaved Changes Handling ---
    def set_dirty(self, dirty_state: bool = True):
        """Sets the dirty state and updates the window title."""
        if self._is_dirty != dirty_state:
            self._is_dirty = dirty_state
            title = APP_NAME
            if self._is_dirty: title += " *"
            self.title(title)

    def _check_unsaved_changes(self) -> bool:
        """Checks if there are unsaved changes and prompts the user. Returns True if OK to proceed, False otherwise."""
        if not self._is_dirty: return True # No changes, safe to proceed
        response = messagebox.askyesnocancel(
            "Unsaved Changes",
            "You have unsaved crops. Do you want to save before proceeding?",
            icon=messagebox.WARNING,
            parent=self
        )
        if response is True:
            self._handle_save()
            # Check dirty state again after save attempt
            return not self._is_dirty
        elif response is False:
            # User chose to discard changes
            return True
        else:
            # User chose to cancel
            return False

    def _on_closing(self):
        """Handles window closing event, checks for unsaved changes."""
        if self._check_unsaved_changes():
            self.destroy()

    # --- Status Bar & UI Updates ---
    def _update_status_bar(self, action_text: Optional[str] = None, coords_text: Optional[str] = None,
                           zoom_text: Optional[str] = None, selection_text: Optional[str] = None):
        """Updates parts of the status bar."""
        # Get current texts to update only specified parts
        current_action = self.lbl_status_action.cget("text")
        current_coords = self.lbl_status_coords.cget("text")
        current_zoom_select = self.lbl_status_zoom_select.cget("text")

        # Split zoom and selection parts
        parts = current_zoom_select.split('|', 1)
        current_zoom_info = parts[0].strip() if parts else f"Zoom: {self.coord_converter.zoom_factor:.1%}"
        current_select_info = parts[1].strip() if len(parts) > 1 else "Sel: ---"


        new_action = action_text if action_text is not None else current_action
        new_coords = coords_text if coords_text is not None else current_coords
        new_zoom_info = zoom_text if zoom_text is not None else current_zoom_info
        new_select_info = selection_text if selection_text is not None else current_select_info

        self.lbl_status_action.configure(text=new_action)
        self.lbl_status_coords.configure(text=new_coords)
        self.lbl_status_zoom_select.configure(text=f"{new_zoom_info} | {new_select_info}")


    def _update_status_bar_selection_info(self):
        """Updates the selection part of the status bar."""
        selection_text = " Sel: --- "
        selected_crop = self.crop_manager.get_selected_crop()
        if selected_crop:
            coords = selected_crop.coords
            if coords and len(coords) == 4:
                # Calculate width and height in image pixels
                width = coords[2] - coords[0]
                height = coords[3] - coords[1]
                selection_text = f" Sel: {max(0, width)}x{max(0, height)} px" # Show non-negative size
        self._update_status_bar(selection_text=selection_text)


    def _update_canvas_cursor(self, cursor_style: str):
        """Sets the canvas cursor style."""
        try:
            self.canvas.config(cursor=cursor_style)
        except tk.TclError:
            # Fallback for potentially unsupported cursors
            print(f"Warning: Cursor style '{cursor_style}' might not be supported. Using default.")
            self.canvas.config(cursor="")


    def _on_crops_changed(self):
        """Callback from CropManager when crops are added, deleted, or modified."""
        self.set_dirty(True)
        # Update save button states based on whether there are crops
        has_crops = bool(self.crop_manager.crops)
        self.btn_save.configure(state=tk.NORMAL if has_crops else tk.DISABLED)
        self.btn_save_as.configure(state=tk.NORMAL if has_crops else tk.DISABLED)


    def _on_selection_changed(self, selected_crop_id: Optional[str]):
        """Callback from CropManager when selected crop changes."""
        is_selected = selected_crop_id is not None
        self.btn_delete_crop.configure(state=tk.NORMAL if is_selected else tk.DISABLED)
        self.btn_rename_crop.configure(state=tk.NORMAL if is_selected else tk.DISABLED)
        self._update_status_bar_selection_info()


    # --- Keyboard Shortcut Handlers ---
    def _handle_delete_event(self, event=None):
        """Handles the Delete key press."""
        # Delegate delete action to a dedicated method that checks selection
        self._delete_selected_crop()
        return "break" # Prevent default widget behavior

    def _delete_selected_crop(self):
        """Deletes the currently selected crop."""
        if self.crop_manager and self.crop_manager.selected_crop_id:
            self.crop_manager.delete_crop(self.crop_manager.selected_crop_id)
            self._update_status_bar(action_text="Crop Deleted")


    def _handle_nudge(self, dx_img: int, dy_img: int):
        """Handles arrow key nudge."""
        if self.crop_manager and self.crop_manager.nudge_selected_crop(dx_img, dy_img):
            self._update_status_bar(action_text="Nudged")
            self._update_status_bar_selection_info() # Size might not change, but coords did


    def _handle_resize_key(self, dx_img: int, dy_img: int, handle_dir: str):
        """Handles Shift+arrow key resize."""
        if self.crop_manager and self.crop_manager.resize_selected_crop_key(dx_img, dy_img, handle_dir):
             self._update_status_bar(action_text="Resized")
             self._update_status_bar_selection_info()


    # --- Window Resize Handling ---
    def _on_window_resize(self, event=None):
        """Handles window resize event. Schedules a canvas redraw."""
        # Delay redraw slightly to avoid excessive redraws during interactive resizing
        self.after(10, self._perform_delayed_resize_update)

    def _perform_delayed_resize_update(self):
        """Performs canvas redraw after a small delay on window resize."""
        # Recalculate zoom/pan to keep image centered if image was smaller than canvas
        if self._original_image is not None:
             canvas_w, canvas_h = self.canvas.winfo_width(), self.canvas.winfo_height()
             img_w, img_h = self._original_image.size

             # Only adjust if the image was fitted *inside* the canvas originally
             # or if canvas size changed significantly
             current_zoom = self.coord_converter.zoom_factor

             # Calculate new offset to keep image centered *relative to canvas center*
             # Find the image coords at the canvas center
             canvas_center_x, canvas_center_y = canvas_w / 2.0, canvas_h / 2.0
             img_center_x_before, img_center_y_before = self.coord_converter.canvas_to_image(canvas_center_x, canvas_center_y)

             if img_center_x_before is not None:
                  # Calculate new offset based on keeping that image point at the new canvas center
                  new_offset_x = canvas_center_x - (img_center_x_before * current_zoom)
                  new_offset_y = canvas_center_y - (img_center_y_before * current_zoom)

                  # Update coordinate converter and redraw
                  self.coord_converter.set_zoom_pan(current_zoom, new_offset_x, new_offset_y)
                  if self.canvas_handler:
                      self.canvas_handler._redraw_canvas_content()

        # Update status bar zoom (it might not change, but refreshes layout)
        self._update_status_bar(zoom_text=f"Zoom: {self.coord_converter.zoom_factor:.1%}")


# --- Run the Application ---
if __name__ == "__main__":
    app = MultiCropApp()
    app.mainloop()
