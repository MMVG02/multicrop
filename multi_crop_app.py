import tkinter as tk
from tkinter import filedialog, messagebox, Listbox, simpledialog
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import uuid
import math
from collections import OrderedDict # To potentially maintain order if needed, but a list of IDs is simpler

# --- Constants ---
RECT_TAG_PREFIX = "crop_rect_"
DEFAULT_RECT_COLOR = "red"
SELECTED_RECT_COLOR = "blue"
RECT_WIDTH = 2
MIN_CROP_SIZE = 10 # Minimum width/height for a crop in pixels

# --- Main Application Class ---
class MultiCropApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Multi Image Cropper")
        self.geometry("1000x700")
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        # --- State Variables ---
        self.image_path = None
        self.original_image = None # Stores the original PIL Image
        self.display_image = None  # Stores the potentially resized PIL Image for display
        self.tk_image = None       # Stores the PhotoImage for the canvas

        # Crop Data: Store data by unique ID
        # { crop_id: {'coords': (x1,y1,x2,y2), 'name': user_defined_name, 'rect_id': canvas_rect_id} }
        self.crop_data = {}
        # Crop Order: Store IDs in the desired order (for listbox display and saving)
        self.crop_order = []

        self.selected_crop_id = None

        # Drawing/Editing State
        self.start_x = None
        self.start_y = None
        self.current_rect_id = None # Temporary rect ID while drawing
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None # 'nw', 'ne', etc.
        self.move_offset_x = 0
        self.move_offset_y = 0
        self.start_coords_img = None # Store image coords when starting move/resize

        # Zoom/Pan State
        self.zoom_factor = 1.0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.is_panning = False
        self.canvas_offset_x = 0 # How much the image top-left is offset on the canvas
        self.canvas_offset_y = 0

        # Listbox Drag & Drop State
        self._drag_data = {"item": None, "index": None, "y": 0} # For listbox drag/drop

        # --- UI Layout ---
        self.grid_columnconfigure(0, weight=3) # Image area
        self.grid_columnconfigure(1, weight=1) # Control panel
        self.grid_rowconfigure(0, weight=1)

        # Left Frame (Image Display)
        self.image_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.image_frame.grid_rowconfigure(0, weight=1)
        self.image_frame.grid_columnconfigure(0, weight=1)

        # Canvas for image and rectangles
        self.canvas = tk.Canvas(self.image_frame, bg="gray90", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # Right Frame (Controls)
        self.control_frame = ctk.CTkFrame(self, width=250)
        self.control_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False)
        self.control_frame.grid_rowconfigure(3, weight=1) # Listbox takes space
        self.control_frame.grid_columnconfigure(0, weight=1)

        # Buttons
        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image", command=self.select_image)
        self.btn_select_image.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        self.btn_save_crops = ctk.CTkButton(self.control_frame, text="Save All Crops", command=self.save_crops, state=tk.DISABLED)
        self.btn_save_crops.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        # Crop List Label
        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List:")
        self.lbl_crop_list.grid(row=2, column=0, padx=10, pady=(10, 0), sticky="w")

        # Crop Listbox with Scrollbar
        self.listbox_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.listbox_frame.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")
        self.listbox_frame.grid_columnconfigure(0, weight=1)
        self.listbox_frame.grid_rowconfigure(0, weight=1)

        self.crop_listbox = Listbox(self.listbox_frame,
                                    bg='white', fg='black',
                                    selectbackground='#CDEAFE',
                                    selectforeground='black',
                                    highlightthickness=1, highlightbackground="#CCCCCC",
                                    highlightcolor="#89C4F4",
                                    borderwidth=0, exportselection=False,
                                    selectmode=tk.EXTENDED) # Enable multi-selection
        self.crop_listbox.grid(row=0, column=0, sticky="nsew")

        self.listbox_scrollbar = ctk.CTkScrollbar(self.listbox_frame, command=self.crop_listbox.yview)
        self.listbox_scrollbar.grid(row=0, column=1, sticky="ns")
        self.crop_listbox.config(yscrollcommand=self.listbox_scrollbar.set)

        # Bind listbox events
        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        self.crop_listbox.bind("<Double-Button-1>", self.on_listbox_double_click) # For renaming
        self.crop_listbox.bind("<ButtonPress-1>", self._on_listbox_press)       # For drag/drop
        self.crop_listbox.bind("<B1-Motion>", self._on_listbox_drag)           # For drag/drop
        self.crop_listbox.bind("<ButtonRelease-1>", self._on_listbox_release)   # For drag/drop

        # Delete Button
        self.btn_delete_crop = ctk.CTkButton(self.control_frame, text="Delete Selected Crop(s)",
                                             command=self.delete_selected_crops,
                                             state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F")
        self.btn_delete_crop.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")

        # --- Canvas Bindings ---
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<ButtonPress-3>", self.on_right_click) # Right-click binding
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<ButtonPress-4>", lambda e: self.on_mouse_wheel(e, 1)) # Linux scroll up
        self.canvas.bind("<ButtonPress-5>", lambda e: self.on_mouse_wheel(e, -1)) # Linux scroll down
        self.canvas.bind("<ButtonPress-2>", self.on_pan_press)
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)
        self.canvas.bind("<Motion>", self.update_cursor)
        self.bind("<Delete>", self.delete_selected_crops_event) # Bind Delete key
        self.bind("<Configure>", self.on_window_resize)

    # --- Image Handling ---
    def select_image(self):
        path = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff")]
        )
        if not path:
            return

        try:
            self.image_path = path
            self.original_image = Image.open(self.image_path)

            self.update_idletasks()
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            if canvas_width <= 1 or canvas_height <= 1:
                print("Warning: Canvas size not available for initial fit.")
                canvas_width, canvas_height = 600, 500 # Fallback

            img_width, img_height = self.original_image.size
            if img_width == 0 or img_height == 0:
                 raise ValueError("Image has zero dimension")

            zoom_h = canvas_width / img_width
            zoom_v = canvas_height / img_height
            initial_zoom = min(zoom_h, zoom_v)
            padding_factor = 0.98
            self.zoom_factor = min(1.0, initial_zoom) * padding_factor

            display_w = img_width * self.zoom_factor
            display_h = img_height * self.zoom_factor
            self.canvas_offset_x = math.ceil((canvas_width - display_w) / 2)
            self.canvas_offset_y = math.ceil((canvas_height - display_h) / 2)

            self.clear_crops_and_list() # Clear previous state
            self.display_image_on_canvas()
            self.btn_save_crops.configure(state=tk.DISABLED) # Disabled until crops are made

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open or process image:\n{e}")
            self.image_path = None
            self.original_image = None
            self.clear_crops_and_list()
            self.canvas.delete("all")
            self.tk_image = None
            self.display_image = None
            self.btn_save_crops.configure(state=tk.DISABLED)

    def clear_crops_and_list(self):
        """Clears existing crops, listbox, and resets related states."""
        self.canvas.delete("crop_rect") # Delete only crop rectangles
        self.crop_data.clear()
        self.crop_order.clear()
        self.populate_crop_listbox() # Clear listbox via repopulate
        self.selected_crop_id = None
        self.btn_delete_crop.configure(state=tk.DISABLED)
        self.btn_save_crops.configure(state=tk.DISABLED) # Ensure save button is disabled

    def display_image_on_canvas(self):
        """Displays the current self.display_image on the canvas respecting zoom and pan."""
        if not self.original_image:
            self.canvas.delete("all")
            return

        disp_w = int(self.original_image.width * self.zoom_factor)
        disp_h = int(self.original_image.height * self.zoom_factor)

        disp_w = max(1, disp_w)
        disp_h = max(1, disp_h)

        try:
            self.display_image = self.original_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
            self.tk_image = ImageTk.PhotoImage(self.display_image)
        except Exception as e:
             print(f"Error resizing image: {e}")
             self.display_image = None
             self.canvas.delete("all")
             return

        self.canvas.delete("all") # Clear everything

        int_offset_x = int(round(self.canvas_offset_x))
        int_offset_y = int(round(self.canvas_offset_y))

        self.canvas_image_id = self.canvas.create_image(
            int_offset_x, int_offset_y,
            anchor=tk.NW, image=self.tk_image, tags="image"
        )

        self.redraw_all_crops()

    # --- Coordinate Conversion ---
    def canvas_to_image_coords(self, canvas_x, canvas_y):
        """Convert canvas coordinates to original image coordinates."""
        if not self.original_image or self.zoom_factor == 0: return None, None
        img_x = (canvas_x - self.canvas_offset_x) / self.zoom_factor
        img_y = (canvas_y - self.canvas_offset_y) / self.zoom_factor
        return img_x, img_y

    def image_to_canvas_coords(self, img_x, img_y):
        """Convert original image coordinates to canvas coordinates."""
        if not self.original_image: return None, None
        canvas_x = (img_x * self.zoom_factor) + self.canvas_offset_x
        canvas_y = (img_y * self.zoom_factor) + self.canvas_offset_y
        return canvas_x, canvas_y

    # --- Crop Handling ---
    def add_crop(self, x1_img, y1_img, x2_img, y2_img):
        """Adds a new crop definition and draws it."""
        if not self.original_image: return

        img_w, img_h = self.original_image.size
        # Clamp coordinates to image bounds
        x1_img = max(0.0, min(x1_img, img_w))
        y1_img = max(0.0, min(y1_img, img_h))
        x2_img = max(0.0, min(x2_img, img_w))
        y2_img = max(0.0, min(y2_img, img_h))

        # Ensure x1 < x2, y1 < y2
        final_x1 = min(x1_img, x2_img)
        final_y1 = min(y1_img, y2_img)
        final_x2 = max(x1_img, x2_img)
        final_y2 = max(y1_img, y2_img)

        if (final_x2 - final_x1) < MIN_CROP_SIZE or (final_y2 - final_y1) < MIN_CROP_SIZE:
            print("Crop too small, ignoring.")
            if self.current_rect_id: self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            return

        coords = (final_x1, final_y1, final_x2, final_y2)
        crop_id = str(uuid.uuid4())
        default_name = f"Crop {len(self.crop_order) + 1}"

        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])

        if cx1 is None:
            print("Error: Cannot draw crop, coordinate conversion failed.")
            return

        rect_id = self.canvas.create_rectangle(
            cx1, cy1, cx2, cy2,
            outline=DEFAULT_RECT_COLOR, width=RECT_WIDTH,
            tags=(RECT_TAG_PREFIX + crop_id, "crop_rect")
        )

        self.crop_data[crop_id] = {
            'coords': coords,
            'name': default_name, # Store a default user-editable name
            'rect_id': rect_id
        }
        self.crop_order.append(crop_id) # Add ID to the end of the ordered list

        self.populate_crop_listbox() # Update listbox display
        self.select_crop(crop_id, from_listbox=False) # Select the new crop

        self.btn_save_crops.configure(state=tk.NORMAL)
        self.btn_delete_crop.configure(state=tk.NORMAL)

    def select_crop(self, crop_id, from_listbox=True):
        """Selects a crop by its ID, updates visuals and listbox."""
        # Deselect previous
        if self.selected_crop_id and self.selected_crop_id in self.crop_data:
            prev_rect_id = self.crop_data[self.selected_crop_id]['rect_id']
            if prev_rect_id in self.canvas.find_withtag(prev_rect_id):
                 self.canvas.itemconfig(prev_rect_id, outline=DEFAULT_RECT_COLOR)

        self.selected_crop_id = crop_id

        # Select new
        if crop_id and crop_id in self.crop_data:
            rect_id = self.crop_data[crop_id]['rect_id']
            if rect_id in self.canvas.find_all():
                 self.canvas.itemconfig(rect_id, outline=SELECTED_RECT_COLOR)
                 self.canvas.tag_raise(rect_id)
                 self.btn_delete_crop.configure(state=tk.NORMAL)

                 # Update listbox selection if not triggered by it
                 if not from_listbox:
                     index = self.get_listbox_index_from_crop_id(crop_id)
                     if index != -1:
                         self.crop_listbox.selection_clear(0, tk.END)
                         self.crop_listbox.selection_set(index)
                         self.crop_listbox.activate(index)
                         self.crop_listbox.see(index)
            else:
                 # Stale rect_id
                 print(f"Warning: Stale rectangle ID {rect_id} for crop {crop_id}")
                 self.selected_crop_id = None
                 self.btn_delete_crop.configure(state=tk.DISABLED)
                 if not from_listbox: self.crop_listbox.selection_clear(0, tk.END) # Clear listbox selection if internal select failed
        else:
            # No valid crop selected or crop_id is None
            self.selected_crop_id = None
            if not from_listbox:
                self.crop_listbox.selection_clear(0, tk.END)
            self.btn_delete_crop.configure(state=tk.DISABLED)

    def update_crop_coords(self, crop_id, new_img_coords):
        """Updates the stored original image coordinates for a crop, with bounds/size checks."""
        if crop_id in self.crop_data and self.original_image:
            img_w, img_h = self.original_image.size
            x1, y1, x2, y2 = new_img_coords
            x1 = max(0.0, min(x1, img_w))
            y1 = max(0.0, min(y1, img_h))
            x2 = max(0.0, min(x2, img_w))
            y2 = max(0.0, min(y2, img_h))

            final_x1 = min(x1, x2)
            final_y1 = min(y1, y2)
            final_x2 = max(x1, x2)
            final_y2 = max(y1, y2)

            if (final_x2 - final_x1) < MIN_CROP_SIZE or (final_y2 - final_y1) < MIN_CROP_SIZE:
                # print("Debug: Crop update rejected due to min size violation")
                return False

            self.crop_data[crop_id]['coords'] = (final_x1, final_y1, final_x2, final_y2)
            return True
        return False

    def redraw_all_crops(self):
        """Redraws all rectangles based on stored coords and current view."""
        # Clear existing crop rectangles from canvas first
        self.canvas.delete("crop_rect")

        for crop_id in self.crop_order: # Iterate in order
            if crop_id not in self.crop_data: continue # Should not happen if lists are in sync

            data = self.crop_data[crop_id]
            img_x1, img_y1, img_x2, img_y2 = data['coords']
            cx1, cy1 = self.image_to_canvas_coords(img_x1, img_y1)
            cx2, cy2 = self.image_to_canvas_coords(img_x2, img_y2)

            if cx1 is None: continue

            color = SELECTED_RECT_COLOR if crop_id == self.selected_crop_id else DEFAULT_RECT_COLOR
            tags_tuple = (RECT_TAG_PREFIX + crop_id, "crop_rect")

            # Recreate the rectangle
            rect_id = self.canvas.create_rectangle(
                 cx1, cy1, cx2, cy2,
                 outline=color, width=RECT_WIDTH,
                 tags=tags_tuple
             )
            # Update the stored rect_id (it changes when recreated)
            self.crop_data[crop_id]['rect_id'] = rect_id

        # Ensure selected is on top
        if self.selected_crop_id and self.selected_crop_id in self.crop_data:
            selected_rect_id = self.crop_data[self.selected_crop_id]['rect_id']
            if selected_rect_id in self.canvas.find_all():
                 self.canvas.tag_raise(selected_rect_id)

    def delete_selected_crops_event(self, event=None):
        """Handles delete key press."""
        self.delete_selected_crops()

    def delete_selected_crops(self):
        """Deletes the currently selected crops from the listbox."""
        selected_indices = list(self.crop_listbox.curselection()) # Get selected indices
        if not selected_indices: return

        # Get the IDs to delete *before* modifying crop_order
        ids_to_delete = [self.get_crop_id_from_listbox_index(i) for i in selected_indices]
        ids_to_delete = [id for id in ids_to_delete if id is not None] # Filter out potential errors

        if not ids_to_delete: return

        # Determine which item index to try selecting next
        # This logic is a bit tricky with multi-delete.
        # Simplest is to try selecting the first item after the block of deleted items,
        # or the new last item if the end of the list was deleted.
        min_deleted_index = min(selected_indices)
        next_select_index = -1 # Will be determined after deletion

        # Delete from internal data structures
        for crop_id in ids_to_delete:
            if crop_id in self.crop_data:
                # Remove from canvas
                rect_id = self.crop_data[crop_id]['rect_id']
                if rect_id in self.canvas.find_all():
                    self.canvas.delete(rect_id)

                # Remove from dictionary
                del self.crop_data[crop_id]

                # Remove from order list
                if crop_id in self.crop_order:
                    self.crop_order.remove(crop_id)

        # Reset selection state if the selected crop was deleted
        if self.selected_crop_id in ids_to_delete:
            self.selected_crop_id = None

        # Update listbox display
        self.populate_crop_listbox()

        # Attempt to select an item after deletion
        if self.crop_listbox.size() > 0:
            # Select the item that is now at the position of the first deleted item, or the last item
            new_index_to_select = min(min_deleted_index, self.crop_listbox.size() - 1)
            self.crop_listbox.selection_set(new_index_to_select)
            self.on_listbox_select() # Trigger selection logic

        # Update button states
        self.btn_delete_crop.configure(state=tk.DISABLED if not self.crop_order else tk.NORMAL)
        self.btn_save_crops.configure(state=tk.DISABLED if not self.crop_order else tk.NORMAL)


    # --- Mouse Event Handlers (Canvas) ---
    def on_mouse_press(self, event):
        self.canvas.focus_set() # Set focus for key events
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        # Ignore if right-click (handled by on_right_click) or middle-click (handled by pan)
        if event.num == 3 or event.num == 2:
            return

        # Check if clicking on a resize handle of the selected crop
        handle = self.get_resize_handle(canvas_x, canvas_y)
        if handle and self.selected_crop_id:
            self.is_resizing = True
            self.resize_handle = handle
            self.start_x = canvas_x
            self.start_y = canvas_y
            self.start_coords_img = self.crop_data[self.selected_crop_id]['coords'] # Store original image coords
            return

        # Check if clicking inside an existing rectangle to select/move it
        clicked_crop_id = self.find_crop_at_canvas_coords(canvas_x, canvas_y)

        if clicked_crop_id:
            self.select_crop(clicked_crop_id)
            self.is_moving = True
            rect_coords = self.canvas.coords(self.crop_data[clicked_crop_id]['rect_id'])
            self.move_offset_x = canvas_x - rect_coords[0]
            self.move_offset_y = canvas_y - rect_coords[1]
            return

        # If not clicking on handle or rect, start drawing
        if self.original_image:
             self.is_drawing = True
             self.start_x = canvas_x
             self.start_y = canvas_y
             self.current_rect_id = self.canvas.create_rectangle(
                 self.start_x, self.start_y, self.start_x, self.start_y,
                 outline=SELECTED_RECT_COLOR, width=RECT_WIDTH, dash=(4, 4),
                 tags=("temp_rect",)
             )
             self.select_crop(None) # Deselect any current crop

    def on_right_click(self, event):
        self.canvas.focus_set() # Set focus for key events
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        # Find crop at click location
        clicked_crop_id = self.find_crop_at_canvas_coords(canvas_x, canvas_y)

        if clicked_crop_id:
             # Select the crop if one is found
             self.select_crop(clicked_crop_id)
             # TODO: Could potentially add a context menu here later
        else:
             # If clicked outside any crop, deselect
             self.select_crop(None)

        return "break" # Prevent default right-click menu

    def find_crop_at_canvas_coords(self, canvas_x, canvas_y):
        """Finds the topmost crop rectangle at given canvas coordinates."""
        # Find items tagged "crop_rect" near the click
        overlapping_items = self.canvas.find_overlapping(canvas_x-1, canvas_y-1, canvas_x+1, canvas_y+1)
        clicked_crop_id = None
        # Iterate in reverse to get the topmost visible item
        for item_id in reversed(overlapping_items):
             tags = self.canvas.gettags(item_id)
             # Check if the item has the crop rectangle prefix tag
             crop_id_tag = next((tag for tag in tags if tag.startswith(RECT_TAG_PREFIX)), None)
             if crop_id_tag:
                  crop_id = crop_id_tag[len(RECT_TAG_PREFIX):]
                  if crop_id in self.crop_data:
                       clicked_crop_id = crop_id
                       break # Found the topmost crop rect

        return clicked_crop_id


    def on_mouse_drag(self, event):
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self.is_drawing and self.current_rect_id:
            self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, canvas_x, canvas_y)

        elif self.is_moving and self.selected_crop_id:
            crop_id = self.selected_crop_id
            rect_id = self.crop_data[crop_id]['rect_id']
            current_canvas_coords = self.canvas.coords(rect_id)
            w = current_canvas_coords[2] - current_canvas_coords[0]
            h = current_canvas_coords[3] - current_canvas_coords[1]

            new_cx1 = canvas_x - self.move_offset_x
            new_cy1 = canvas_y - self.move_offset_y
            new_cx2 = new_cx1 + w
            new_cy2 = new_cy1 + h

            img_x1, img_y1 = self.canvas_to_image_coords(new_cx1, new_cy1)
            img_x2, img_y2 = self.canvas_to_image_coords(new_cx2, new_cy2)

            if img_x1 is not None:
                updated = self.update_crop_coords(crop_id, (img_x1, img_y1, img_x2, img_y2))
                if updated:
                     validated_img_coords = self.crop_data[crop_id]['coords']
                     cx1_final, cy1_final = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                     cx2_final, cy2_final = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                     self.canvas.coords(rect_id, cx1_final, cy1_final, cx2_final, cy2_final)

        elif self.is_resizing and self.selected_crop_id and self.resize_handle:
            crop_id = self.selected_crop_id
            rect_id = self.crop_data[crop_id]['rect_id']

            ox1_img, oy1_img, ox2_img, oy2_img = self.start_coords_img

            curr_img_x, curr_img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
            start_img_x, start_img_y = self.canvas_to_image_coords(self.start_x, self.start_y)

            if curr_img_x is None or start_img_x is None: return

            dx_img = curr_img_x - start_img_x
            dy_img = curr_img_y - start_img_y

            nx1, ny1, nx2, ny2 = ox1_img, oy1_img, ox2_img, oy2_img

            if 'n' in self.resize_handle: ny1 += dy_img
            if 's' in self.resize_handle: ny2 += dy_img
            if 'w' in self.resize_handle: nx1 += dx_img
            if 'e' in self.resize_handle: nx2 += dx_img

            updated = self.update_crop_coords(crop_id, (nx1, ny1, nx2, ny2))

            if updated:
                 validated_img_coords = self.crop_data[crop_id]['coords']
                 cx1_final, cy1_final = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                 cx2_final, cy2_final = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                 self.canvas.coords(rect_id, cx1_final, cy1_final, cx2_final, cy2_final)

    def on_mouse_release(self, event):
        if self.is_drawing and self.current_rect_id:
            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            if self.current_rect_id in self.canvas.find_withtag("temp_rect"):
                self.canvas.delete(self.current_rect_id)

            img_x1, img_y1 = self.canvas_to_image_coords(self.start_x, self.start_y)
            img_x2, img_y2 = self.canvas_to_image_coords(canvas_x, canvas_y)

            if img_x1 is not None and img_y1 is not None and img_x2 is not None and img_y2 is not None:
                 self.add_crop(img_x1, img_y1, img_x2, img_y2)
            else:
                 print("Failed to add crop due to coordinate conversion error.")

        # Reset states
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.current_rect_id = None
        self.start_coords_img = None
        self.update_cursor(event)

    # --- Zoom and Pan Handlers ---
    def on_mouse_wheel(self, event, direction=None):
        if not self.original_image: return

        if direction:
            delta = direction
        elif event.num == 5 or event.delta < 0:
            delta = -1
        elif event.num == 4 or event.delta > 0:
            delta = 1
        else:
            return

        zoom_increment = 1.1
        min_zoom = 0.01
        max_zoom = 20.0

        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)

        img_x_before, img_y_before = self.canvas_to_image_coords(canvas_x, canvas_y)
        if img_x_before is None: return

        if delta > 0:
            new_zoom = self.zoom_factor * zoom_increment
        else:
            new_zoom = self.zoom_factor / zoom_increment
        new_zoom = max(min_zoom, min(max_zoom, new_zoom))

        if new_zoom == self.zoom_factor: return

        self.zoom_factor = new_zoom

        self.canvas_offset_x = canvas_x - (img_x_before * self.zoom_factor)
        self.canvas_offset_y = canvas_y - (img_y_before * self.zoom_factor)

        self.display_image_on_canvas()

    def on_pan_press(self, event):
        if not self.original_image: return
        self.is_panning = True
        self.pan_start_x = self.canvas.canvasx(event.x)
        self.pan_start_y = self.canvas.canvasy(event.y)
        self.canvas.config(cursor="fleur")

    def on_pan_drag(self, event):
        if not self.is_panning or not self.original_image: return
        current_x = self.canvas.canvasx(event.x)
        current_y = self.canvas.canvasy(event.y)
        dx = current_x - self.pan_start_x
        dy = current_y - self.pan_start_y

        self.canvas_offset_x += dx
        self.canvas_offset_y += dy

        self.canvas.move("all", dx, dy)

        self.pan_start_x = current_x
        self.pan_start_y = current_y

    def on_pan_release(self, event):
        self.is_panning = False
        self.update_cursor(event)

    # --- Listbox Handling ---
    def populate_crop_listbox(self):
        """Clears and repopulates the listbox based on the current crop_order."""
        self.crop_listbox.delete(0, tk.END)
        for i, crop_id in enumerate(self.crop_order):
            if crop_id in self.crop_data:
                # Display format: index+1. User_Defined_Name
                display_name = f"{i+1}. {self.crop_data[crop_id].get('name', 'Unnamed Crop')}"
                self.crop_listbox.insert(tk.END, display_name)
            else:
                 print(f"Warning: crop_id {crop_id} in order but not in crop_data.")
                 # Optionally, remove the orphaned ID from crop_order here.

        # Re-select the current item in the listbox if it still exists
        if self.selected_crop_id:
            index = self.get_listbox_index_from_crop_id(self.selected_crop_id)
            if index != -1:
                self.crop_listbox.selection_set(index)
                self.crop_listbox.activate(index)
                self.crop_listbox.see(index)

    def get_crop_id_from_listbox_index(self, index):
        """Gets the internal crop_id from a listbox index."""
        if 0 <= index < len(self.crop_order):
            return self.crop_order[index]
        return None

    def get_listbox_index_from_crop_id(self, crop_id):
        """Gets the listbox index from an internal crop_id."""
        try:
            return self.crop_order.index(crop_id)
        except ValueError:
            return -1 # Not found

    def on_listbox_select(self, event=None):
        selection = self.crop_listbox.curselection()
        if not selection:
            # Selection cleared in listbox
            if self.selected_crop_id:
                self.select_crop(None, from_listbox=True)
            self.btn_delete_crop.configure(state=tk.DISABLED)
            return

        # Get the ID of the *first* selected item (for single canvas selection)
        selected_index = selection[0]
        selected_crop_id = self.get_crop_id_from_listbox_index(selected_index)

        if selected_crop_id:
             self.select_crop(selected_crop_id, from_listbox=True)
             self.btn_delete_crop.configure(state=tk.NORMAL) # Enable delete if any item is selected
        else:
             print(f"Warning: Could not get crop_id for listbox index {selected_index}")
             self.select_crop(None, from_listbox=True)
             self.btn_delete_crop.configure(state=tk.DISABLED)

    def on_listbox_double_click(self, event):
        """Handle double-click to rename a crop."""
        selected_indices = self.crop_listbox.curselection()
        if not selected_indices: return
        selected_index = selected_indices[0] # Only rename the first selected one
        crop_id = self.get_crop_id_from_listbox_index(selected_index)

        if crop_id and crop_id in self.crop_data:
            current_name = self.crop_data[crop_id].get('name', '')
            # Use CTkInputDialog for consistency
            dialog = ctk.CTkInputDialog(text="Enter new crop name:", title="Rename Crop")
            new_name = dialog.get_input() # Waits for user input

            if new_name is not None and new_name.strip() != "": # Check if user entered text and didn't cancel
                 self.crop_data[crop_id]['name'] = new_name.strip()
                 self.populate_crop_listbox() # Update listbox display
                 # Re-select the item after renaming
                 self.select_crop(crop_id, from_listbox=False)
            elif new_name is not None: # User entered empty string
                 messagebox.showwarning("Rename Crop", "Crop name cannot be empty.")


    # --- Listbox Drag and Drop ---
    def _on_listbox_press(self, event):
        # Ignore if multi-selecting or right-click
        if event.state & (1<<0) or event.state & (1<<2) or event.num == 3: # Check Ctrl/Shift or Right click
            return

        clicked_index = self.crop_listbox.nearest(event.y)
        if clicked_index == -1: return # Clicked outside items

        # Ensure only the clicked item is selected for dragging
        self.crop_listbox.selection_clear(0, tk.END)
        self.crop_listbox.selection_set(clicked_index)
        self.on_listbox_select() # Ensure canvas selection updates

        # Store drag data
        self._drag_data["item"] = self.get_crop_id_from_listbox_index(clicked_index)
        self._drag_data["index"] = clicked_index
        self._drag_data["y"] = event.y

        # Optional: Change cursor to indicate dragging
        self.crop_listbox.config(cursor="fleur")


    def _on_listbox_drag(self, event):
        if self._drag_data["item"] is None: return

        # Get the index of the item currently under the mouse
        current_index = self.crop_listbox.nearest(event.y)

        # Optional: Visual feedback - change background of item under cursor
        # Clear previous highlight
        if self._drag_data.get("highlighted_index") is not None and \
           self._drag_data["highlighted_index"] != current_index:
             try:
                 self.crop_listbox.itemconfigure(self._drag_data["highlighted_index"], background="white")
             except tk.TclError: pass # Handle case where item might have been removed somehow

        # Highlight current item if it's a different item
        if current_index != -1 and current_index != self._drag_data["index"]:
            try:
                self.crop_listbox.itemconfigure(current_index, background="#E0E0E0") # Light gray highlight
                self._drag_data["highlighted_index"] = current_index
            except tk.TclError: pass


    def _on_listbox_release(self, event):
        if self._drag_data["item"] is None:
            # If no drag was initiated, but it was a single click, ensure selection
            if self.crop_listbox.curselection():
                 self.on_listbox_select()
            # Reset cursor anyway
            self.crop_listbox.config(cursor="")
            return

        # Get the index where the item was dropped
        drop_index = self.crop_listbox.nearest(event.y)

        # Clear the highlight
        if self._drag_data.get("highlighted_index") is not None:
             try:
                 self.crop_listbox.itemconfigure(self._drag_data["highlighted_index"], background="white")
             except tk.TclError: pass
             self._drag_data["highlighted_index"] = None


        # Perform the reorder if the item was dropped on a valid index and it's different
        if drop_index != -1 and drop_index != self._drag_data["index"]:
            item_id_to_move = self._drag_data["item"]
            original_index = self._drag_data["index"]

            # Remove the item_id from its original position
            if item_id_to_move in self.crop_order:
                 self.crop_order.remove(item_id_to_move)
            else:
                 print("Error: Dragged item ID not found in crop_order.")
                 self._reset_listbox_drag_state() # Clean up state
                 return

            # Insert the item_id at the new position
            # Need to adjust drop_index if inserting *after* its original position
            insert_index = drop_index
            # If moving down the list, the index calculation needs care.
            # If the item started at index 3 and is moved *after* the item now at index 5,
            # the list shrunk by 1 before insertion, so inserting at index 5 puts it
            # after the item that was originally at index 4 (now index 5).
            # A simpler way: remove, then insert at the target index. If moving from lower
            # index to higher index, the target index effectively becomes target_index - 1
            # because the list shrinks before insertion.
            if original_index < drop_index:
                 insert_index = drop_index # Insert *after* the item that is now at drop_index

            self.crop_order.insert(insert_index, item_id_to_move)

            # Update the listbox display to reflect the new order and numbering
            self.populate_crop_listbox()

            # Keep the moved item selected
            new_index = self.get_listbox_index_from_crop_id(item_id_to_move)
            if new_index != -1:
                 self.crop_listbox.selection_clear(0, tk.END)
                 self.crop_listbox.selection_set(new_index)
                 self.crop_listbox.activate(new_index)
                 self.crop_listbox.see(new_index) # Ensure visible

        self._reset_listbox_drag_state() # Reset drag state

    def _reset_listbox_drag_state(self):
        """Resets the internal drag state variables and cursor."""
        self._drag_data = {"item": None, "index": None, "y": 0, "highlighted_index": None}
        self.crop_listbox.config(cursor="") # Reset cursor


    # --- Resizing Helpers ---
    def get_resize_handle(self, canvas_x, canvas_y):
        """Checks if the cursor is near a resize handle of the selected crop."""
        if not self.selected_crop_id or self.selected_crop_id not in self.crop_data:
            return None

        rect_id = self.crop_data[self.selected_crop_id]['rect_id']
        if rect_id not in self.canvas.find_all():
            return None

        cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
        handle_margin = 6

        # Check corners first
        if abs(canvas_x - cx1) < handle_margin and abs(canvas_y - cy1) < handle_margin: return 'nw'
        if abs(canvas_x - cx2) < handle_margin and abs(canvas_y - cy1) < handle_margin: return 'ne'
        if abs(canvas_x - cx1) < handle_margin and abs(canvas_y - cy2) < handle_margin: return 'sw'
        if abs(canvas_x - cx2) < handle_margin and abs(canvas_y - cy2) < handle_margin: return 'se'

        # Check edges
        inner_buffer = handle_margin / 2
        if abs(canvas_y - cy1) < handle_margin and (cx1 + inner_buffer) < canvas_x < (cx2 - inner_buffer): return 'n'
        if abs(canvas_y - cy2) < handle_margin and (cx1 + inner_buffer) < canvas_x < (cx2 - inner_buffer): return 's'
        if abs(canvas_x - cx1) < handle_margin and (cy1 + inner_buffer) < canvas_y < (cy2 - inner_buffer): return 'w'
        if abs(canvas_x - cx2) < handle_margin and (cy1 + inner_buffer) < canvas_y < (cy2 - inner_buffer): return 'e'

        return None

    def update_cursor(self, event=None):
        """Changes the mouse cursor based on position relative to selected crop or panning state."""
        if self.is_panning:
            self.canvas.config(cursor="fleur")
            return
        if self.is_drawing or self.is_resizing or self.is_moving: # Don't change cursor mid-action
            return

        new_cursor = ""

        if event:
            canvas_x = self.canvas.canvasx(event.x)
            canvas_y = self.canvas.canvasy(event.y)
            handle = self.get_resize_handle(canvas_x, canvas_y)

            if handle:
                cursor_map = {'nw': 'size_nw_se', 'se': 'size_nw_se',
                              'ne': 'size_ne_sw', 'sw': 'size_ne_sw',
                              'n': 'size_ns', 's': 'size_ns',
                              'e': 'size_we', 'w': 'size_we'}
                new_cursor = cursor_map.get(handle, "")
            else:
                # Check if hovering inside the *selected* rectangle for move indication
                if self.selected_crop_id and self.selected_crop_id in self.crop_data:
                     rect_id = self.crop_data[self.selected_crop_id]['rect_id']
                     if rect_id in self.canvas.find_all():
                         cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
                         if cx1 < canvas_x < cx2 and cy1 < canvas_y < cy2:
                             new_cursor = "fleur"

        if self.canvas.cget("cursor") != new_cursor:
             self.canvas.config(cursor=new_cursor)

    # --- Window Resize Handling ---
    def on_window_resize(self, event=None):
        # If the window resizes, the canvas will resize automatically.
        # We don't strictly need to refit the image, existing pan/zoom applies.
        # Redrawing crops might be needed if the canvas coordinates change layout slightly?
        # The current redraw_all_crops handles converting stored image coords to new canvas coords,
        # so it should be OK without an explicit redraw here unless canvas origin shifts.
        # CTk handles the layout, so probably not needed.
        pass # Keep for potential future use

    # --- Saving Crops ---
    def save_crops(self):
        if not self.original_image or not self.image_path:
            messagebox.showwarning("No Image", "Please select an image first.")
            return
        if not self.crop_order:
            messagebox.showwarning("No Crops", "Please define at least one crop area.")
            return

        base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        # Create folder in the same directory as the image file
        # output_dir = os.path.join(os.path.dirname(self.image_path), base_name)
        # Or in the same directory as the script/executable:
        output_dir = os.path.abspath(base_name)


        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Directory Error", f"Could not create output directory:\n{output_dir}\n{e}")
            return

        saved_count = 0
        error_count = 0

        # Iterate through crop_order to save sequentially
        for i, crop_id in enumerate(self.crop_order):
            if crop_id not in self.crop_data: continue # Skip if somehow not in data

            data = self.crop_data[crop_id]
            coords = tuple(map(int, data['coords'])) # Ensure integer coords for cropping
            # Filename: base_name_N.jpg (N is 1-based index from crop_order)
            filename = f"{base_name}_{i+1}.jpg"
            filepath = os.path.join(output_dir, filename)

            try:
                cropped_img = self.original_image.crop(coords)
                if cropped_img.mode in ('RGBA', 'P'):
                    cropped_img = cropped_img.convert('RGB')
                cropped_img.save(filepath, "JPEG", quality=95)
                saved_count += 1
            except Exception as e:
                error_count += 1
                print(f"Error saving {filename}: {e}")

        if error_count == 0:
            messagebox.showinfo("Success", f"Successfully saved {saved_count} crops to the '{base_name}' folder.")
        else:
            messagebox.showwarning("Partial Success", f"Saved {saved_count} crops to '{base_name}'.\nFailed to save {error_count} crops. Check console for details.")


# --- Run the Application ---
if __name__ == "__main__":
    app = MultiCropApp()
    app.mainloop()
