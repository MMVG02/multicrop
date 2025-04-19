import tkinter as tk
from tkinter import filedialog, messagebox, Listbox
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import uuid # To generate unique IDs for crops initially

# --- Constants ---
RECT_TAG_PREFIX = "crop_rect_"
DEFAULT_RECT_COLOR = "red"
SELECTED_RECT_COLOR = "blue"
RECT_WIDTH = 2
MIN_CROP_SIZE = 10 # Minimum width/height for a crop in pixels
OUTPUT_FOLDER = "cropped_images"

# --- Main Application Class ---
class MultiCropApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Multi Image Cropper")
        self.geometry("1000x700") # Adjust size as needed
        ctk.set_appearance_mode("System") # System, Dark, Light
        ctk.set_default_color_theme("blue") # "blue", "green", "dark-blue"

        # --- State Variables ---
        self.image_path = None
        self.original_image = None # Stores the original PIL Image
        self.display_image = None  # Stores the potentially resized PIL Image for display
        self.tk_image = None       # Stores the PhotoImage for the canvas
        self.canvas_image_id = None # ID of the image item on the canvas
        self.crops = {}            # Dictionary to store crop data {crop_id: {'coords': (x1,y1,x2,y2), 'name': name, 'rect_id': canvas_rect_id}}
        self.selected_crop_id = None
        self.next_crop_number = 1

        # Drawing/Editing State
        self.start_x = None
        self.start_y = None
        self.current_rect_id = None
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None # 'nw', 'ne', 'sw', 'se', 'n', 's', 'e', 'w'
        self.move_offset_x = 0
        self.move_offset_y = 0

        # Zoom/Pan State
        self.zoom_factor = 1.0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.is_panning = False
        self.canvas_offset_x = 0 # How much the image top-left is offset on the canvas
        self.canvas_offset_y = 0

        # --- UI Layout ---
        self.grid_columnconfigure(0, weight=3) # Image area takes more space
        self.grid_columnconfigure(1, weight=1) # Control panel
        self.grid_rowconfigure(0, weight=1)

        # --- Left Frame (Image Display) ---
        self.image_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.image_frame.grid_rowconfigure(0, weight=1)
        self.image_frame.grid_columnconfigure(0, weight=1)

        # Canvas for image and rectangles
        self.canvas = tk.Canvas(self.image_frame, bg="gray20", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # --- Right Frame (Controls) ---
        self.control_frame = ctk.CTkFrame(self, width=250)
        self.control_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False) # Prevent frame from shrinking
        self.control_frame.grid_rowconfigure(3, weight=1) # Listbox takes available space
        self.control_frame.grid_columnconfigure(0, weight=1)

        # Buttons
        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image", command=self.select_image)
        self.btn_select_image.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        self.btn_save_crops = ctk.CTkButton(self.control_frame, text="Save All Crops", command=self.save_crops, state=tk.DISABLED)
        self.btn_save_crops.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        # Crop List Label
        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List:")
        self.lbl_crop_list.grid(row=2, column=0, padx=10, pady=(10, 0), sticky="w")

        # Crop Listbox
        self.crop_listbox = Listbox(self.control_frame, bg="#2D2D2D", fg="white",
                                    selectbackground="#1F6AA5", # Match CTk blue theme
                                    highlightthickness=1, highlightbackground="#565B5E",
                                    borderwidth=0, exportselection=False) # exportselection=False allows canvas interaction while listbox item is selected
        self.crop_listbox.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")
        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)

        # Delete Button
        self.btn_delete_crop = ctk.CTkButton(self.control_frame, text="Delete Selected Crop", command=self.delete_selected_crop, state=tk.DISABLED)
        self.btn_delete_crop.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")

        # --- Canvas Bindings ---
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel) # Windows/macOS specific delta
        self.canvas.bind("<ButtonPress-4>", lambda e: self.on_mouse_wheel(e, 1)) # Linux scroll up
        self.canvas.bind("<ButtonPress-5>", lambda e: self.on_mouse_wheel(e, -1)) # Linux scroll down
        self.canvas.bind("<ButtonPress-2>", self.on_pan_press) # Middle mouse button for panning
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)
        self.canvas.bind("<Motion>", self.update_cursor) # For resize handles
        self.bind("<Delete>", self.delete_selected_crop_event) # Bind Delete key

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
            # Reset everything for the new image
            self.reset_view()
            self.display_image_on_canvas()
            self.btn_save_crops.configure(state=tk.NORMAL if self.crops else tk.DISABLED)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open image:\n{e}")
            self.image_path = None
            self.original_image = None
            self.btn_save_crops.configure(state=tk.DISABLED)

    def reset_view(self):
        """Resets zoom, pan, crops for a new image or view change."""
        self.canvas.delete("all") # Clear canvas
        self.crops.clear()
        self.crop_listbox.delete(0, tk.END)
        self.selected_crop_id = None
        self.next_crop_number = 1
        self.zoom_factor = 1.0
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0
        self.tk_image = None
        self.display_image = None
        self.btn_delete_crop.configure(state=tk.DISABLED)
        self.btn_save_crops.configure(state=tk.DISABLED)

    def display_image_on_canvas(self):
        """Displays the current self.display_image on the canvas respecting zoom and pan."""
        if not self.original_image:
            return

        # Calculate display size based on zoom
        disp_w = int(self.original_image.width * self.zoom_factor)
        disp_h = int(self.original_image.height * self.zoom_factor)

        # Only resize if needed to avoid quality loss on minor zooms? Maybe not needed.
        # Let's always resize based on zoom factor for consistency
        try:
            # Use LANCZOS for better quality resizing
            self.display_image = self.original_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        except ValueError: # Handle cases where size is 0
             self.display_image = self.original_image # Fallback if resize fails
        except Exception as e:
             print(f"Error resizing image: {e}")
             self.display_image = self.original_image # Fallback

        self.tk_image = ImageTk.PhotoImage(self.display_image)

        # Clear previous image and rectangles before drawing new ones
        self.canvas.delete("all")

        # Draw image at current pan offset
        self.canvas_image_id = self.canvas.create_image(
            self.canvas_offset_x, self.canvas_offset_y,
            anchor=tk.NW, image=self.tk_image, tags="image"
        )

        # Redraw all crop rectangles based on new zoom/pan
        self.redraw_all_crops()


    # --- Coordinate Conversion ---
    def canvas_to_image_coords(self, canvas_x, canvas_y):
        """Convert canvas coordinates to original image coordinates."""
        if not self.original_image: return None, None
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

        # Ensure coordinates are within image bounds and valid
        img_w, img_h = self.original_image.size
        x1_img = max(0, min(x1_img, img_w))
        y1_img = max(0, min(y1_img, img_h))
        x2_img = max(0, min(x2_img, img_w))
        y2_img = max(0, min(y2_img, img_h))

        # Ensure width/height are minimal
        if abs(x2_img - x1_img) < MIN_CROP_SIZE or abs(y2_img - y1_img) < MIN_CROP_SIZE:
            print("Crop too small, ignoring.")
            if self.current_rect_id: self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            return

        # Ensure x1 < x2 and y1 < y2
        coords = (min(x1_img, x2_img), min(y1_img, y2_img),
                  max(x1_img, x2_img), max(y1_img, y2_img))

        crop_id = str(uuid.uuid4()) # Unique ID for this crop
        crop_name = f"Crop_{self.next_crop_number}"
        self.next_crop_number += 1

        # Convert image coords back to canvas coords for drawing
        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])

        # Create the rectangle on the canvas
        rect_id = self.canvas.create_rectangle(
            cx1, cy1, cx2, cy2,
            outline=DEFAULT_RECT_COLOR, width=RECT_WIDTH,
            tags=(RECT_TAG_PREFIX + crop_id, "crop_rect") # Tag with unique ID and general tag
        )

        # Store crop data
        self.crops[crop_id] = {
            'coords': coords, # Store ORIGINAL image coordinates
            'name': crop_name,
            'rect_id': rect_id
        }

        # Add to listbox and select it
        self.crop_listbox.insert(tk.END, crop_name)
        self.crop_listbox.selection_clear(0, tk.END)
        self.crop_listbox.selection_set(tk.END)
        self.select_crop(crop_id, from_listbox=False)

        self.btn_save_crops.configure(state=tk.NORMAL)
        self.btn_delete_crop.configure(state=tk.NORMAL)

    def select_crop(self, crop_id, from_listbox=True):
        """Selects a crop by its ID, updates visuals."""
        if self.selected_crop_id == crop_id:
            return # Already selected

        # Deselect previous
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            prev_rect_id = self.crops[self.selected_crop_id]['rect_id']
            self.canvas.itemconfig(prev_rect_id, outline=DEFAULT_RECT_COLOR)

        self.selected_crop_id = crop_id

        # Select new
        if crop_id and crop_id in self.crops:
            rect_id = self.crops[crop_id]['rect_id']
            self.canvas.itemconfig(rect_id, outline=SELECTED_RECT_COLOR)
            self.canvas.tag_raise(rect_id) # Bring selected rectangle to front
            self.btn_delete_crop.configure(state=tk.NORMAL)

            # Update listbox selection if not triggered by it
            if not from_listbox:
                index = -1
                for i in range(self.crop_listbox.size()):
                    if self.crop_listbox.get(i) == self.crops[crop_id]['name']:
                        index = i
                        break
                if index != -1:
                    self.crop_listbox.selection_clear(0, tk.END)
                    self.crop_listbox.selection_set(index)
                    self.crop_listbox.activate(index)
                    self.crop_listbox.see(index) # Ensure visible
        else:
            self.selected_crop_id = None # No valid crop selected
            self.btn_delete_crop.configure(state=tk.DISABLED)


    def update_crop_coords(self, crop_id, new_img_coords):
        """Updates the stored original image coordinates for a crop."""
        if crop_id in self.crops:
             # Ensure coordinates are valid and within bounds
            img_w, img_h = self.original_image.size
            x1, y1, x2, y2 = new_img_coords
            x1 = max(0, min(x1, img_w))
            y1 = max(0, min(y1, img_h))
            x2 = max(0, min(x2, img_w))
            y2 = max(0, min(y2, img_h))
            # Ensure x1 < x2, y1 < y2
            self.crops[crop_id]['coords'] = (min(x1,x2), min(y1,y2), max(x1,x2), max(y1,y2))


    def redraw_all_crops(self):
        """Redraws all rectangles based on stored coords and current view."""
        for crop_id, data in self.crops.items():
            img_x1, img_y1, img_x2, img_y2 = data['coords']
            cx1, cy1 = self.image_to_canvas_coords(img_x1, img_y1)
            cx2, cy2 = self.image_to_canvas_coords(img_x2, img_y2)

            color = SELECTED_RECT_COLOR if crop_id == self.selected_crop_id else DEFAULT_RECT_COLOR

            if data['rect_id'] in self.canvas.find_all():
                 # If rectangle exists, update its coordinates and color
                 self.canvas.coords(data['rect_id'], cx1, cy1, cx2, cy2)
                 self.canvas.itemconfig(data['rect_id'], outline=color)
            else:
                 # If rectangle doesn't exist (e.g., after image reload), recreate it
                 rect_id = self.canvas.create_rectangle(
                     cx1, cy1, cx2, cy2,
                     outline=color, width=RECT_WIDTH,
                     tags=(RECT_TAG_PREFIX + crop_id, "crop_rect")
                 )
                 self.crops[crop_id]['rect_id'] = rect_id # Update stored rect_id

            # Ensure selected is on top
            if crop_id == self.selected_crop_id:
                 self.canvas.tag_raise(data['rect_id'])


    def delete_selected_crop_event(self, event=None):
        """Handles delete key press."""
        self.delete_selected_crop()

    def delete_selected_crop(self):
        """Deletes the currently selected crop."""
        if not self.selected_crop_id or self.selected_crop_id not in self.crops:
            return

        crop_id_to_delete = self.selected_crop_id
        data = self.crops[crop_id_to_delete]

        # Remove from canvas
        self.canvas.delete(data['rect_id'])

        # Remove from listbox
        index = -1
        for i in range(self.crop_listbox.size()):
            if self.crop_listbox.get(i) == data['name']:
                index = i
                break
        if index != -1:
            self.crop_listbox.delete(index)

        # Remove from internal dictionary
        del self.crops[crop_id_to_delete]

        # Reset selection state
        self.selected_crop_id = None
        self.btn_delete_crop.configure(state=tk.DISABLED)
        if not self.crops:
             self.btn_save_crops.configure(state=tk.DISABLED)

        # Select the next item in the list if possible
        if self.crop_listbox.size() > 0:
            new_index = max(0, index -1) if index != -1 else 0 # Select previous or first
            self.crop_listbox.selection_set(new_index)
            self.on_listbox_select() # Trigger selection logic
        else:
            self.select_crop(None) # Deselect completely


    # --- Mouse Event Handlers ---
    def on_mouse_press(self, event):
        self.canvas.focus_set() # Set focus to canvas for keyboard events (like Delete)
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        # Check if clicking on a resize handle of the selected crop
        handle = self.get_resize_handle(canvas_x, canvas_y)
        if handle and self.selected_crop_id:
            self.is_resizing = True
            self.resize_handle = handle
            self.start_x = canvas_x
            self.start_y = canvas_y
            # Store the original image coords *before* resizing starts
            self.start_coords_img = self.crops[self.selected_crop_id]['coords']
            return

        # Check if clicking inside an existing rectangle to select/move it
        clicked_item = self.canvas.find_closest(canvas_x, canvas_y)
        if clicked_item:
            tags = self.canvas.gettags(clicked_item[0])
            if tags and tags[0].startswith(RECT_TAG_PREFIX):
                crop_id = tags[0][len(RECT_TAG_PREFIX):]
                if crop_id in self.crops:
                    self.select_crop(crop_id)
                    self.is_moving = True
                    # Record mouse offset relative to the top-left corner of the rect
                    rect_coords = self.canvas.coords(self.crops[crop_id]['rect_id'])
                    self.move_offset_x = canvas_x - rect_coords[0]
                    self.move_offset_y = canvas_y - rect_coords[1]
                    return # Don't start drawing a new rectangle

        # If not clicking on a handle or existing rect, start drawing a new one
        self.is_drawing = True
        self.start_x = canvas_x
        self.start_y = canvas_y
        # Create a temporary dashed rectangle
        self.current_rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline=SELECTED_RECT_COLOR, width=RECT_WIDTH, dash=(4, 4)
        )
        # Deselect any currently selected crop
        self.select_crop(None)


    def on_mouse_drag(self, event):
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self.is_drawing and self.current_rect_id:
            # Update the temporary drawing rectangle
            self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, canvas_x, canvas_y)

        elif self.is_moving and self.selected_crop_id:
            crop_id = self.selected_crop_id
            rect_id = self.crops[crop_id]['rect_id']
            current_canvas_coords = self.canvas.coords(rect_id)
            w = current_canvas_coords[2] - current_canvas_coords[0]
            h = current_canvas_coords[3] - current_canvas_coords[1]

            # New top-left based on where the mouse is, considering the initial click offset
            new_cx1 = canvas_x - self.move_offset_x
            new_cy1 = canvas_y - self.move_offset_y
            new_cx2 = new_cx1 + w
            new_cy2 = new_cy1 + h

            # Update canvas rectangle position
            self.canvas.coords(rect_id, new_cx1, new_cy1, new_cx2, new_cy2)

            # Convert new canvas coords back to original image coords and update storage
            img_x1, img_y1 = self.canvas_to_image_coords(new_cx1, new_cy1)
            img_x2, img_y2 = self.canvas_to_image_coords(new_cx2, new_cy2)
            if img_x1 is not None: # Check conversion was successful
                 self.update_crop_coords(crop_id, (img_x1, img_y1, img_x2, img_y2))

        elif self.is_resizing and self.selected_crop_id and self.resize_handle:
            crop_id = self.selected_crop_id
            rect_id = self.crops[crop_id]['rect_id']

            # Get original image coordinates before this drag started
            ox1_img, oy1_img, ox2_img, oy2_img = self.start_coords_img

            # Calculate mouse delta in canvas coordinates
            dx = canvas_x - self.start_x
            dy = canvas_y - self.start_y

            # Calculate mouse delta in original image coordinates (approximately)
            dx_img = dx / self.zoom_factor
            dy_img = dy / self.zoom_factor

            # Calculate new proposed image coordinates based on handle
            nx1, ny1, nx2, ny2 = ox1_img, oy1_img, ox2_img, oy2_img

            if 'n' in self.resize_handle: ny1 += dy_img
            if 's' in self.resize_handle: ny2 += dy_img
            if 'w' in self.resize_handle: nx1 += dx_img
            if 'e' in self.resize_handle: nx2 += dx_img

            # Basic validation: prevent flipping and ensure min size
            min_w_img = MIN_CROP_SIZE / self.zoom_factor
            min_h_img = MIN_CROP_SIZE / self.zoom_factor

            if nx2 - nx1 < min_w_img:
                 if 'w' in self.resize_handle: nx1 = nx2 - min_w_img
                 else: nx2 = nx1 + min_w_img # 'e' handle
            if ny2 - ny1 < min_h_img:
                 if 'n' in self.resize_handle: ny1 = ny2 - min_h_img
                 else: ny2 = ny1 + min_h_img # 's' handle

            # Ensure order (x1 < x2, y1 < y2) after potential swaps
            final_x1 = min(nx1, nx2)
            final_y1 = min(ny1, ny2)
            final_x2 = max(nx1, nx2)
            final_y2 = max(ny1, ny2)

            # Update the stored original image coordinates
            self.update_crop_coords(crop_id, (final_x1, final_y1, final_x2, final_y2))

            # Convert updated image coords back to canvas coords for drawing
            cx1, cy1 = self.image_to_canvas_coords(final_x1, final_y1)
            cx2, cy2 = self.image_to_canvas_coords(final_x2, final_y2)

            # Update the canvas rectangle
            self.canvas.coords(rect_id, cx1, cy1, cx2, cy2)


    def on_mouse_release(self, event):
        if self.is_drawing and self.current_rect_id:
            # Finalize the new crop
            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            self.canvas.delete(self.current_rect_id) # Delete the temporary dashed rect

            # Convert start and end canvas coords to image coords
            img_x1, img_y1 = self.canvas_to_image_coords(self.start_x, self.start_y)
            img_x2, img_y2 = self.canvas_to_image_coords(canvas_x, canvas_y)

            if img_x1 is not None: # Check conversion success
                 self.add_crop(img_x1, img_y1, img_x2, img_y2)

        # Reset states
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.current_rect_id = None
        self.start_x = None
        self.start_y = None
        self.update_cursor(event) # Reset cursor


    # --- Zoom and Pan Handlers ---
    def on_mouse_wheel(self, event, direction=None):
        if not self.original_image: return

        # Determine scroll direction (platform differences)
        if direction: # Linux binding provides direction
            delta = direction
        elif event.num == 5 or event.delta < 0: # Scroll down
            delta = -1
        elif event.num == 4 or event.delta > 0: # Scroll up
            delta = 1
        else:
            return # Should not happen

        # --- Zooming logic ---
        zoom_increment = 1.1
        min_zoom = 0.1
        max_zoom = 10.0 # Adjust limits as needed

        # Get mouse position on canvas - this is the zoom center
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)

        # Calculate what point on the *original image* is under the mouse *before* zoom
        img_x_before, img_y_before = self.canvas_to_image_coords(canvas_x, canvas_y)

        # Calculate new zoom factor
        if delta > 0: # Zoom in
            new_zoom = self.zoom_factor * zoom_increment
        else: # Zoom out
            new_zoom = self.zoom_factor / zoom_increment
        new_zoom = max(min_zoom, min(max_zoom, new_zoom)) # Clamp zoom factor

        if new_zoom == self.zoom_factor: return # No change

        self.zoom_factor = new_zoom

        # Calculate where the image point (img_x_before, img_y_before) should be
        # on the canvas *after* zooming, relative to the canvas origin (0,0).
        # It should still be under the mouse pointer (canvas_x, canvas_y).
        # canvas_x = (img_x_before * new_zoom_factor) + new_offset_x
        # canvas_y = (img_y_before * new_zoom_factor) + new_offset_y
        # Solve for new_offset_x, new_offset_y:
        self.canvas_offset_x = canvas_x - (img_x_before * self.zoom_factor)
        self.canvas_offset_y = canvas_y - (img_y_before * self.zoom_factor)

        # Update the displayed image and redraw crops
        self.display_image_on_canvas()

    def on_pan_press(self, event):
        if not self.original_image: return
        self.is_panning = True
        self.pan_start_x = self.canvas.canvasx(event.x)
        self.pan_start_y = self.canvas.canvasy(event.y)
        self.canvas.config(cursor="fleur") # Change cursor to indicate panning

    def on_pan_drag(self, event):
        if not self.is_panning or not self.original_image: return
        current_x = self.canvas.canvasx(event.x)
        current_y = self.canvas.canvasy(event.y)
        dx = current_x - self.pan_start_x
        dy = current_y - self.pan_start_y

        # Update canvas offset
        self.canvas_offset_x += dx
        self.canvas_offset_y += dy

        # Move the image on the canvas
        self.canvas.move(self.canvas_image_id, dx, dy)

        # Move all crop rectangles
        for crop_id in self.crops:
            rect_id = self.crops[crop_id]['rect_id']
            self.canvas.move(rect_id, dx, dy)

        # Update start position for next drag event
        self.pan_start_x = current_x
        self.pan_start_y = current_y

    def on_pan_release(self, event):
        self.is_panning = False
        self.canvas.config(cursor="") # Reset cursor

    # --- Listbox Selection ---
    def on_listbox_select(self, event=None):
        selection = self.crop_listbox.curselection()
        if not selection:
            self.select_crop(None) # Deselect if nothing is selected in listbox
            return

        selected_index = selection[0]
        selected_name = self.crop_listbox.get(selected_index)

        # Find the crop_id associated with this name
        found_id = None
        for crop_id, data in self.crops.items():
            if data['name'] == selected_name:
                found_id = crop_id
                break

        if found_id:
            self.select_crop(found_id, from_listbox=True)

    # --- Resizing Helpers ---
    def get_resize_handle(self, canvas_x, canvas_y):
        """Checks if the cursor is near a resize handle of the selected crop."""
        if not self.selected_crop_id or self.selected_crop_id not in self.crops:
            return None

        rect_id = self.crops[self.selected_crop_id]['rect_id']
        cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
        handle_margin = 6 # Pixels around corners/edges to detect handle

        on_top = abs(canvas_y - cy1) < handle_margin
        on_bottom = abs(canvas_y - cy2) < handle_margin
        on_left = abs(canvas_x - cx1) < handle_margin
        on_right = abs(canvas_x - cx2) < handle_margin
        in_vertical = cy1 < canvas_y < cy2
        in_horizontal = cx1 < canvas_x < cx2

        if on_top and on_left: return 'nw'
        if on_top and on_right: return 'ne'
        if on_bottom and on_left: return 'sw'
        if on_bottom and on_right: return 'se'
        if on_top and in_horizontal: return 'n'
        if on_bottom and in_horizontal: return 's'
        if on_left and in_vertical: return 'w'
        if on_right and in_vertical: return 'e'

        return None

    def update_cursor(self, event=None):
        """Changes the mouse cursor based on position relative to selected crop."""
        if self.is_panning:
            self.canvas.config(cursor="fleur")
            return
        if self.is_moving:
            self.canvas.config(cursor="fleur") # Or use "hand2" or "grabbing" if available
            return
        if self.is_resizing or self.is_drawing: # Let resize/draw dictate cursor
            return # Already handled potentially

        # If not actively doing something, check for hover
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        handle = self.get_resize_handle(canvas_x, canvas_y)

        new_cursor = "" # Default cursor
        if handle:
             # Map handle to appropriate Tk cursor names
            if handle in ('nw', 'se'): new_cursor = "size_nw_se"
            elif handle in ('ne', 'sw'): new_cursor = "size_ne_sw"
            elif handle in ('n', 's'): new_cursor = "size_ns"
            elif handle in ('e', 'w'): new_cursor = "size_we"
        else:
            # Check if hovering inside the selected rectangle (for move indication)
            if self.selected_crop_id and self.selected_crop_id in self.crops:
                 rect_id = self.crops[self.selected_crop_id]['rect_id']
                 cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
                 if cx1 < canvas_x < cx2 and cy1 < canvas_y < cy2:
                     new_cursor = "fleur" # Indicate movability

        self.canvas.config(cursor=new_cursor)


    # --- Saving Crops ---
    def save_crops(self):
        if not self.original_image:
            messagebox.showwarning("No Image", "Please select an image first.")
            return
        if not self.crops:
            messagebox.showwarning("No Crops", "Please define at least one crop area.")
            return

        # Ensure output directory exists
        try:
            os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Directory Error", f"Could not create output directory:\n{OUTPUT_FOLDER}\n{e}")
            return

        saved_count = 0
        error_count = 0

        # Sort crops by name (which are sequential like Crop_1, Crop_2) for ordered saving
        # This requires parsing the number from the name
        def get_crop_num(item):
            try:
                return int(item[1]['name'].split('_')[-1])
            except:
                return float('inf') # Put unparsable names last

        sorted_crop_items = sorted(self.crops.items(), key=get_crop_num)


        for crop_id, data in sorted_crop_items:
            # Get ORIGINAL image coordinates, ensuring they are integers
            coords = tuple(map(int, data['coords']))
            crop_name = data['name']
            filename = f"{crop_name}.jpg"
            filepath = os.path.join(OUTPUT_FOLDER, filename)

            try:
                # Crop the *original* image
                cropped_img = self.original_image.crop(coords)

                # Convert to RGB before saving as JPG if necessary (e.g., if original is RGBA or P)
                if cropped_img.mode in ('RGBA', 'P'):
                    cropped_img = cropped_img.convert('RGB')

                # Save as JPG
                cropped_img.save(filepath, "JPEG", quality=95) # Adjust quality as needed
                saved_count += 1
                print(f"Saved: {filepath}")

            except Exception as e:
                error_count += 1
                print(f"Error saving {filename}: {e}")
                # Consider showing an error message for each failure or just a summary

        # Show summary message
        if error_count == 0:
            messagebox.showinfo("Success", f"Successfully saved {saved_count} crops to the '{OUTPUT_FOLDER}' folder.")
        else:
            messagebox.showwarning("Partial Success", f"Saved {saved_count} crops.\nFailed to save {error_count} crops. Check console/log for details.")


# --- Run the Application ---
if __name__ == "__main__":
    app = MultiCropApp()
    app.mainloop()
