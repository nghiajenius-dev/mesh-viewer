"""STL/OBJ Python Mesh Viewer prototype with Plotly/CEF Webview/Tkinter
using a Model View Controller (MVC) design.

This is just a simple prototype/proof-of-concept and not intended to
be a full fledged application. If you are interested in custom CAE and
simulation tools such as this app and
[FEATool Multiphysics](https://www.featool.com) please feel free to
get in touch with [Precise Simulation](https://www.precisesimulation.com).

:license: AGPL v3, see LICENSE for more details or contact
          Precise Simulation for alternative licensing options.
:copyright: 2020 Precise Simulation Ltd.

"""

try:
    import tkinter as tk
except ImportError:
    import Tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as tkfont
from tkinter.filedialog import askopenfilename

from cefpython3 import cefpython as cef
import ctypes
import sys
import platform

WIDTH  = 640
HEIGHT = 550


class Model():

    def __init__(self, data=None):

        # Define unit cube.
        if data is None:
            vertices = [[0,0,0], [1,0,0], [1,1,0], [0,1,0],
                        [0,0,1], [1,0,1], [1,1,1], [0,1,1]]
            faces = [[1,2,3], [1,3,4], [1,2,6], [1,6,5], [2,3,7], [2,7,6], \
                     [3,4,8], [3,8,7], [4,1,5], [4,5,8], [5,6,7], [5,7,8]]
            data = Mesh(vertices, faces)

        self.data = [data]

    def clear(self):
        self.data = []

    def load_file(self, file_name):
        '''Load mesh from file
        '''
        if file_name.lower().endswith(('.stl','.stla')):
            mesh = self.load_stl(file_name)

        elif file_name.lower().endswith('.obj'):
            mesh = self.load_obj(file_name)

        self.data.append(mesh)

    def load_stl(self, file_name):
        '''Load STL CAD file
        '''
        try:
            with open(file_name, 'r') as f:
                data = f.read()

        except:
            return self.load_stl_with_numpy_stl(file_name)

        vertices = []
        faces = []
        v = []
        for i, line in enumerate(data.splitlines()):
            if i == 0 and line.strip() != 'solid':
                raise ValueError('Not valid ASCII STL file.')

            line_data = line.split()

            if line_data[0]=='facet':
                v = []

            elif line_data[0]=='vertex':
                v.append([float(line_data[1]), float(line_data[2]), float(line_data[3])])

            elif line_data[0]=='endloop':
                if len(v)==3:
                    vertices.extend(v)
                    ind = 3*len(faces)+1
                    faces.append([ind, ind+1, ind+2])

        return Mesh(vertices, faces)

    def load_stl_with_numpy_stl(self, file_name):
        import numpy as np
        from stl import mesh
        msh = mesh.Mesh.from_file(file_name)
        vertices = np.concatenate(msh.vectors)
        n_faces = len(msh.vectors)
        faces = np.array(range(3*n_faces)).reshape(n_faces,3) + 1
        return Mesh(vertices, faces)

    def load_obj(self, file_name):
        '''Load ASCII Wavefront OBJ CAD file
        '''
        with open(file_name, 'r') as f:
            data = f.read()

        vertices = []
        faces = []
        for line in data.splitlines():
            line_data = line.split()
            if line_data:
                if line_data[0] == 'v':
                    v = [float(line_data[1]), float(line_data[2]), float(line_data[3])]
                    vertices.append(v)
                elif line_data[0] == 'f':
                    face = []
                    for i in range(1, len(line_data)):
                        s = line_data[i].replace('//','/').split('/')
                        face.append(int(s[0]))

                    faces.append(face)

        return Mesh(vertices, faces)

    def get_bounding_box(self):
        bbox = self.data[0].bounding_box
        for mesh in self.data[1:]:
            for i in range(len(bbox)):
                x_i = mesh.bounding_box[i]
                bbox[i][0] = min([bbox[i][0], min(x_i)])
                bbox[i][1] = max([bbox[i][1], max(x_i)])

        return bbox


class Mesh():

    def __init__(self, vertices, faces):
        self.vertices = vertices
        self.faces = faces
        self.bounding_box = self.get_bounding_box()

    def get_vertices(self):
        vertices = []
        for face in self.faces:
            vertices.append([self.vertices[ivt-1] for ivt in face])

        return vertices

    def get_line_segments(self):
        line_segments = set()
        for face in self.faces:
            for i in range(len(face)):
                iv = face[i]
                jv = face[(i+1)%len(face)]
                if jv > iv:
                    edge = (iv, jv)
                else:
                    edge = (jv, iv)

                line_segments.add(edge)

        return [[self.vertices[edge[0]-1], self.vertices[edge[1]-1]] for edge in line_segments]

    def get_bounding_box(self):
        v = [vti for face in self.get_vertices() for vti in face]
        bbox = []
        for i in range(len(self.vertices[0])):
            x_i = [p[i] for p in v]
            bbox.append([min(x_i), max(x_i)])

        return bbox


class View():

    def __init__(self, model=None):

        if model is None:
            model = Model()
        self.model = model

        self.figure = None
        self.axes = None
        self.canvas = None
        self.toolbar = None

    def clear(self):
        s_cmd = 'Plotly.deleteTraces("canvas", [...data.keys()]);'
        self.figure.browser.ExecuteJavascript(s_cmd)

    def update(self):
        s_cmd = self.get_plot_cmd()
        self.figure.browser.ExecuteJavascript(s_cmd)

    def plot(self, types="solid + wireframe"):
        self.clear()
        s_cmd = self.get_model_data(types)
        self.figure.browser.ExecuteJavascript(s_cmd)
        self.update()

    def get_plot_cmd(self):
        s_layout = '{"showlegend": false, "scene": {"aspectratio": {"x": 1, "y": 1, "z": 1}, "aspectmode": "manual"}}'
        s = 'Plotly.plot("canvas", data, ' + s_layout + ', {});'
        return s

    def get_model_data(self, types="solid + wireframe"):

        if isinstance(types, (str,)):
            types = [s.strip() for s in types.split('+')]

        s = 'var data = ['
        for mesh in self.model.data:
            for type in types:

                if type=="solid":
                    s += self.get_plotly_mesh3d_data(mesh) + ', '

                elif type=="wireframe":
                    s += self.get_plotly_scatter3d_data(mesh) + ', '

                else:
                    # Unknown plot type
                    return None

        s = s[:-2] + '];'
        return s

    def get_plotly_mesh3d_data(self, mesh):
        s_x = str([x[0] for x in mesh.vertices])
        s_y = str([x[1] for x in mesh.vertices])
        s_z = str([x[2] for x in mesh.vertices])
        s_i = str([f[0]-1 for f in mesh.faces])
        s_j = str([f[1]-1 for f in mesh.faces])
        s_k = str([f[2]-1 for f in mesh.faces])
        s = '{"type": "mesh3d", "name": "faces", "hoverinfo": "x+y+z", ' + \
            '"x": ' + s_x + ', "y": ' + s_y + ', "z": ' + s_z + ', ' \
            '"i": ' + s_i + ', "j": ' + s_j + ', "k": ' + s_k + ', ' \
            '"showscale": false, "color": "rgb(204,204,255)"}'
        return s

    def get_plotly_scatter3d_data(self, mesh):
        s_x = ''
        s_y = ''
        s_z = ''
        for line in mesh.get_line_segments():
            s_x += str(line[0][0]) + ', ' + str(line[1][0]) + ', null, '
            s_y += str(line[0][1]) + ', ' + str(line[1][1]) + ', null, '
            s_z += str(line[0][2]) + ', ' + str(line[1][2]) + ', null, '

        s_x = s_x[:-8]
        s_y = s_y[:-8]
        s_z = s_z[:-8]

        s = '{"type": "scatter3d", "name": "", "mode": "lines", "hoverinfo": "x+y+z", ' + \
            '"x": [' + s_x + '], "y": [' + s_y + '], "z": [' + s_z + '], "showlegend": false, ' + \
            '"line": {"color": "rgb(0,0,0)", "width": 2, "dash": "solid", "showscale": false}}'
        return s

    def xy(self):
        bbox = self.model.get_bounding_box()
        d = 2*(bbox[2][1] - bbox[2][0])
        s_cmd = 'Plotly.relayout("canvas", {"scene":{"camera":{"eye":{"x":0, "y":0, "z":' + str(d) + '}}}});'
        self.figure.browser.ExecuteJavascript(s_cmd)

    def xz(self):
        bbox = self.model.get_bounding_box()
        d = 2*(bbox[1][1] - bbox[1][0])
        s_cmd = 'Plotly.relayout("canvas", {"scene":{"camera":{"eye":{"x":0, "y":' + str(d) + ', "z":0}}}});'
        self.figure.browser.ExecuteJavascript(s_cmd)

    def yz(self):
        bbox = self.model.get_bounding_box()
        d = 2*(bbox[0][1] - bbox[0][0])
        s_cmd = 'Plotly.relayout("canvas", {"scene":{"camera":{"eye":{"x":' + str(d) + ', "y":0, "z":0}}}});'
        self.figure.browser.ExecuteJavascript(s_cmd)

    def reset(self):
        s_cmd = 'Plotly.relayout("canvas", {"scene": {"aspectratio": {"x": 1, "y": 1, "z": 1}, "aspectmode": "manual"}});'
        self.figure.browser.ExecuteJavascript(s_cmd)


class Controller():

    def __init__(self, view=None):

        root = tk.Tk()
        root.geometry(str(WIDTH) + "x" + str(HEIGHT))
        root.resizable(False, False)
        root.title("Mesh Viewer")

        if view is None:
            view = View(None, root)

        f1 = ttk.Frame(root)
        f1.pack(side=tk.TOP, anchor=tk.W)

        toolbar = [ tk.Button(f1, text="Open"),
                    tk.Button(f1, text="XY", command=view.xy),
                    tk.Button(f1, text="XZ", command=view.xz),
                    tk.Button(f1, text="YZ", command=view.yz),
                    tk.Button(f1, text="Reset", command=view.reset) ]

        f2 = tk.Frame(f1, highlightthickness=1, highlightbackground="gray")
        options = ["solid","wireframe","solid + wireframe"]
        var = tk.StringVar()
        o1 = ttk.OptionMenu(f2, var, options[len(options)-1], *options, command=lambda val: self.view.plot(val))
        o1["menu"].configure(bg="white")
        setMaxWidth(options, o1)
        o1.pack()
        toolbar.append(f2)

        toolbar[0].config(command=lambda: self.open(var))

        [obj.pack(side=tk.LEFT, anchor=tk.W) for obj in toolbar]

        f3 = tk.Frame(root)
        f3.bind("<Configure>", self.on_configure)
        f3.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        view.figure = BrowserFrame(f3, view)
        view.figure.pack(fill=tk.BOTH, expand=True)

        menubar = tk.Menu( root )
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open...", command=self.open)
        file_menu.add_command(label="Exit", command=self.exit)
        menubar.add_cascade(label="File", menu=file_menu)
        root.config(menu=menubar)

        self.root = root
        self.view = view
        self.model = view.model

    def render(self):
        cef.Initialize()
        self.root.mainloop()

    def open(self, var):
        file_name = askopenfilename( title = "Select file to open",
                                     filetypes = (("CAD files","*.obj;*.stl"),
                                                  ("all files","*.*")) )
        self.model.clear()
        self.model.load_file(file_name)
        self.view.plot(var.get())

    def on_configure(self, event):
        if self.view.figure:
            width = event.width
            height = event.height
            self.view.figure.on_mainframe_configure(width, height)

    def exit(self):
        self.model.clear()
        self.view.clear()
        self.root.destroy()
        cef.Shutdown()


def setMaxWidth(stringList, element):
    try:
        f = tkfont.nametofont(element.cget("font"))
        zerowidth = f.measure("0")
    except:
        f = tkfont.nametofont(ttk.Style().lookup("TButton", "font"))
        zerowidth = f.measure("0") - 0.8

    w = max([f.measure(i) for i in stringList])/zerowidth
    element.config(width=int(w))


class App():

    def __init__(self, model=None, view=None, controller=None):
        if model is None:
            model = Model()

        if view is None:
            view = View(model)

        if controller is None:
            controller = Controller(view)

        self.model = model
        self.view = view
        self.controller = controller

    def start(self):
        self.controller.render()


# Platforms
WINDOWS = (platform.system() == "Windows")
LINUX = (platform.system() == "Linux")
MAC = (platform.system() == "Darwin")

class BrowserFrame(tk.Frame):

    def __init__(self, master, view=None, navigation_bar=None):
        self.view = view
        self.navigation_bar = navigation_bar
        self.closing = False
        self.browser = None
        tk.Frame.__init__(self, master)
        self.bind("<FocusIn>", self.on_focus_in)
        self.bind("<FocusOut>", self.on_focus_out)
        self.bind("<Configure>", self.on_configure)
        self.focus_set()

    def embed_browser(self):
        window_info = cef.WindowInfo()
        rect = [0, 0, self.winfo_width(), self.winfo_height()]
        window_info.SetAsChild(self.get_window_handle(), rect)
        self.browser = cef.CreateBrowserSync(window_info, url='about:blank')
        assert self.browser
        self.browser.SetClientHandler(LoadHandler(self))
        self.browser.SetClientHandler(FocusHandler(self))
        self.set_start_url()
        self.message_loop_work()

    def set_start_url(self):
        w = round(WIDTH*0.95)
        h = round(HEIGHT*0.9)

        s_body = '<div id="load">Loading Plotly...</div>' + \
            '<div id="canvas" style="width: ' + str(w) + 'px; height: ' + str(h) + 'px;" class="plotly-graph-div"></div>' + \
            '<script src="https://cdn.plot.ly/plotly-latest.min.js" charset="utf-8"></script>' + \
            '<script>' + \
            self.view.get_model_data() + \
            'var elem = document.getElementById("load"); elem.parentNode.removeChild(elem);' + \
            self.view.get_plot_cmd() + \
            '</script>'

        s_cmd = 'document.open("text/html");' + \
            'document.write(\'<!DOCTYPE HTML><html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"><title>Mesh Viewer</title></head><body>' + \
            s_body + \
            '</body></html>\');document.close();'

        self.browser.StopLoad()
        self.browser.ExecuteJavascript(s_cmd)

    def get_window_handle(self):
        if self.winfo_id() > 0:
            return self.winfo_id()
        elif MAC:
            from AppKit import NSApp
            import objc
            return objc.pyobjc_id(NSApp.windows()[-1].contentView())
        else:
            raise Exception("Couldn't obtain window handle")

    def message_loop_work(self):
        try:
            cef.MessageLoopWork()
            self.after(10, self.message_loop_work)
        except:
            pass

    def on_configure(self, _):
        if not self.browser:
            self.embed_browser()

    def on_root_configure(self):
        if self.browser:
            self.browser.NotifyMoveOrResizeStarted()

    def on_mainframe_configure(self, width, height):
        if self.browser:
            try:
                if WINDOWS:
                    ctypes.windll.user32.SetWindowPos(
                        self.browser.GetWindowHandle(), 0,
                        0, 0, width, height, 0x0002)
                elif LINUX:
                    self.browser.SetBounds(0, 0, width, height)

                self.browser.NotifyMoveOrResizeStarted()
            except:
                pass

    def on_focus_in(self, _):
        if self.browser:
            self.browser.SetFocus(True)

    def on_focus_out(self, _):
        if self.browser:
            self.browser.SetFocus(False)

    def on_root_close(self):
        if self.browser:
            self.browser.CloseBrowser(True)
            self.clear_browser_references()
        self.destroy()

    def clear_browser_references(self):
        self.browser = None

class LoadHandler(object):

    def __init__(self, browser_frame):
        self.browser_frame = browser_frame

    def OnLoadStart(self, browser, **_):
        pass

class FocusHandler(object):

    def __init__(self, browser_frame):
        self.browser_frame = browser_frame

    def OnTakeFocus(self, next_component, **_):
        pass

    def OnSetFocus(self, source, **_):
        return False

    def OnGotFocus(self, **_):
        self.browser_frame.focus_set()


if __name__ == "__main__":

    assert cef.__version__ >= "55.3", "CEF Python v55.3+ required to run this"
    sys.excepthook = cef.ExceptHook   # Shutdown all CEF processes on error
    app = App()
    app.start()
