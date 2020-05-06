import json
import numpy
import os
import imageio
from .tex import make_tex, calculate, combine_pdfs
from .html import make_html
#from .pptx import make_pptx

backends = {
    "tikz": make_tex,
    "pptx": None, #make_pptx,
    "html": make_html,
    "sdl2": None
}

def overwrite(name: list, val, layout: dict):
    if len(name) == 1:
        layout[name[0]] = val
        return
    overwrite(name[1:], val, layout[name[0]])

def replace_option(name: str, val, layout: dict):
    # first.second.third -> [ first, second, third ]
    path = name.split(sep='.')
    overwrite(path, val, layout)

def modify_default_layout(layout_filename: str):
    with open(layout_filename) as json_file:
        user = json.load(json_file)

    default_filename = os.path.join(os.path.dirname(__file__), "default_layout.json")
    with open(default_filename) as json_file:
        default = json.load(json_file)

    for key,val in user.items():
        replace_option(key, val, default)

    return default

def merge_data_into_layout(data, layout):
    directions = ["north", "south", "east", "west"]

    num_rows = len(data["elements"])
    num_cols = len(data["elements"][0])
    layout['num_rows'] = num_rows
    layout['num_columns'] = num_cols

    # initialize empty matrix for elements
    layout["elements_content"] = [[{} for i in range(num_cols)] for i in range (num_rows)]

    for row in range(num_rows):
        for col in range(num_cols):
            elem = layout["elements_content"][row][col]
            data_elem = data["elements"][row][col]

            # copy captions, if set            
            for d in directions:
                try:
                    caption = data_elem["captions"][d]
                except:
                    caption = ""
                elem[d] = caption
    
            # add frame from user (optional, default: no frame)
            try:
                frame = data_elem["frame"]
            except: # do not set the frame
                frame = None
            if frame is not None: elem["frame"] = frame

            # add crop marker (optional, default: no marker)
            try:
                marker = data_elem["crop_marker"]
            except: # do not set marker
                marker = None
            if marker is not None: elem["marker"] = marker

            # add the image data itself (raw): matrix of rgb
            # assert ((data_elem["image"]).shape[2] == 3)
            elem["filename"] = data_elem["image"]


    # add column_titles
    for d in ['north', 'south']:
        # change text color
        try:
            layout["column_titles"][d]["text_color"] = data["column_titles"][d]["text_color"]
        except: # keep default
            pass

        # change background color of column text field
        try:
            layout["column_titles"][d]["background_colors"] = data["column_titles"][d]["background_colors"]
        except: # keep default: [0,0,0]
            pass

        # add content
        try:
            layout["column_titles"][d]["content"] = data["column_titles"][d]["content"]
        except: # set default: list of empty strings
            layout["column_titles"][d]["content"] = [""] * num_cols

    # add row_titles
    for d in ['east', 'west']:
        # change text color
        try:
            layout["row_titles"][d]["text_color"] = data["row_titles"][d]["text_color"]
        except: # keep default
            pass

        # change background color of column text field
        try:
            layout["row_titles"][d]["background_colors"] = data["row_titles"][d]["background_colors"]
        except: # keep default: [0,0,0]
            pass

        # add text-based content
        try:
            layout["row_titles"][d]["content"] = data["row_titles"][d]["content"]
        except: # set default: list of empty strings
            layout["row_titles"][d]["content"] = [""] * num_rows

    # titles
    for d in directions:
        # add text-based content
        try:
            layout['titles'][d]['content'] = data['titles'][d]
        except: # set default: empty string
            layout['titles'][d]['content'] = ''

    # set px size based on the first image
    try:
        first = layout["elements_content"][0][0]["filename"][0]["image"]
    except:
        first = layout["elements_content"][0][0]["filename"]
    layout["img_width_px"] = first.shape[0]
    layout["img_height_px"] = first.shape[1]
    calculate.resize_to_match_total_width(layout)
    return layout

def merge(modules: dict, layouts: dict):
    merged_dicts = []
    for i in range(len(modules)):
        merged_dicts.append(merge_data_into_layout(modules[i], layouts[i]))
    return merged_dicts

def apply_height_and_width(module, height, width):
    module["total_height"] = height
    module["total_width"] = width
    calculate.resize_to_match_total_width(module)

def align_two_modules(data1, data2, combined_width):
    # calculate total widths
    image_width1, image_width2 = calculate.get_body_widths_for_equal_heights(data1, data2, combined_width)
    total_width1 = image_width1 + calculate.get_min_width(data1)
    total_width2 = image_width2 + calculate.get_min_width(data2)

    data1['total_width'] = total_width1
    # data1['element_config']['img_width']  = image_width1
    calculate.resize_to_match_total_width(data1)
    data2['total_width'] = total_width2
    calculate.resize_to_match_total_width(data2)

def align_modules(modules, width):
    num_modules = len(modules)
    assert(num_modules!=0)

    if num_modules == 1:
        modules[0]["total_width"] = width
        calculate.resize_to_match_total_width(modules[0])
        return

    sum_inverse_aspect_ratios = 0
    inverse_aspect_ratios = []
    for m in modules:
        #if matplotlib
        #    sum_inverse_aspect_ratios += 1/a
        image_aspect_ratio = m['img_height_px'] / float(m['img_width_px'])
        a = m['num_rows'] / float(m['num_columns']) * image_aspect_ratio
        sum_inverse_aspect_ratios += 1/a
        inverse_aspect_ratios.append(1/a)

    sum_fixed_deltas = 0
    i = 0
    for m in modules:
        w_fix = calculate.get_min_width(m)
        h_fix = calculate.get_min_height(m)
        sum_fixed_deltas += w_fix - h_fix * inverse_aspect_ratios[i]
        i += 1 

    height = (width - sum_fixed_deltas) / sum_inverse_aspect_ratios

    for m in modules:
        m['total_height'] = height
        calculate.resize_to_match_total_height(m)

def png_export(img_raw, filename):
    imageio.imwrite(filename, img_raw)

def export_raw_img_to_png(module):
    path = os.path.join(os.path.dirname(__file__))
    for row in range(module["num_rows"]):
        for col in range(module["num_columns"]):
            elem = module["elements_content"][row][col]

            # the element can be either a list of multiple images, or one image
            try:
                file = elem["filename"][0]["image"]
                is_multi = True
            except:
                is_multi = False

            if is_multi:
                for i in range(len(elem["filename"])):
                    img_raw = elem["filename"][i]["image"]
                    filename = 'image-'+str(row+1)+'-'+str(col+1) + '-' + str(i+1) +'.png'
                    file_path = os.path.join(path, filename)
                    png_export(img_raw, file_path)
                    elem["filename"][i]["image"] = file_path
            else:
                img_raw = elem["filename"]
                filename = 'image-'+str(row+1)+'-'+str(col+1)+'.png'
                file_path = os.path.join(path, filename)
                png_export(img_raw, file_path)
                elem["filename"] = file_path

def horizontal_figure(modules: "a list of dictionaries, one for each module", 
                      width_cm: float, 
                      backend: "Can be one of: 'tikz', 'pptx', 'html', 'sdl2'"):
    """ 
    Creates a figure by putting modules next to each other, from left to right.
    Aligns the height of the given modules such that they fit the given total width.
    """
    layouts = []
    for m in modules:
        layouts.append(modify_default_layout(m['layout']))

    merged_data = merge(modules, layouts)
    align_modules(merged_data, width_cm*10.)

    for i in range(len(modules)):
        export_raw_img_to_png(merged_data[i])
        backends[backend].generate(merged_data[i], to_path=os.path.join(os.path.dirname(__file__)), filename='gen_tex'+str(i)+'.tex')
    
    combine_pdfs.make_pdf(os.path.dirname(__file__), search_for_filenames='gen_pdf*.pdf')
        