import copy
import math
import numpy as np


def scene_obstacles(scene, profile="initial", overrides=None):
    """Payload removal is conditional on a carrying scene, never global obstacle deletion."""
    if profile not in ("initial", "carrying", "delivered"):
        raise ValueError("unknown scene profile")
    goals = {g["id"]: g["pose"] for g in scene["goals"]}
    result = []
    overrides = overrides or {}
    known = {s["id"] for s in scene["obstacles"]}
    if set(overrides.get("disabled_ids", [])) - known:
        raise ValueError("unknown obstacle id in override")
    for original in scene["obstacles"]:
        s = copy.deepcopy(original)
        if s["id"] in overrides.get("disabled_ids", []):
            continue
        if s["kind"] == "pickup_payload":
            if profile == "carrying":
                continue
            if profile == "delivered":
                delta = np.array(goals["Dropoff_P2"][:2]) - np.array(goals["Pickup_P1"][:2])
                for k in ("min", "max"):
                    s[k][:2] = (np.array(s[k][:2]) + delta).tolist()
        result.append(s)
    result.extend(copy.deepcopy(overrides.get("additional", [])))
    for s in result:
        if len(s["min"]) != 3 or len(s["max"]) != 3 or not np.isfinite(s["min"] + s["max"]).all() or np.any(np.array(s["min"]) >= s["max"]):
            raise ValueError("invalid obstacle bounds: " + s["id"])
    return result


class Grid:
    def __init__(self, bounds, resolution):
        self.bounds = np.asarray(bounds, dtype=float)
        self.resolution = float(resolution)
        if self.resolution <= 0 or not np.isfinite(self.bounds).all() or np.any(self.bounds[2:] <= self.bounds[:2]):
            raise ValueError("invalid grid geometry")
        self.width, self.height = np.ceil((self.bounds[2:] - self.bounds[:2]) / self.resolution).astype(int)
        self.x = self.bounds[0] + (np.arange(self.width) + .5) * self.resolution
        self.y = self.bounds[1] + (np.arange(self.height) + .5) * self.resolution

    def cell(self, x, y):
        if not np.isfinite([x, y]).all() or not (self.bounds[0] <= x < self.bounds[2] and self.bounds[1] <= y < self.bounds[3]):
            raise ValueError("pose outside map")
        return int((x-self.bounds[0])/self.resolution), int((y-self.bounds[1])/self.resolution)

    def world(self, col, row):
        return float(self.x[col]), float(self.y[row])

    def window(self, lo, hi):
        c0, r0 = np.maximum(0, np.floor((np.asarray(lo)-self.bounds[:2])/self.resolution).astype(int))
        c1, r1 = np.minimum([self.width, self.height], np.ceil((np.asarray(hi)-self.bounds[:2])/self.resolution).astype(int)+1)
        return slice(r0, max(r0, r1)), slice(c0, max(c0, c1))


def build_mode(grid, solids, mode, margin=.02, headings=8):
    """SAT Minkowski tests; each free cell certifies its full square, not just its centre.

    All obstacles remain 3-D boxes. Robot layers avoid falsely blocking underneath
    overhead conveyors or allowing a tall payload through a low beam.
    Rotation uses a conservative swept disk for each height layer.
    """
    if margin < 0 or headings != 8:
        raise ValueError("nonnegative margin and eight headings required")
    blocked = np.zeros((headings, grid.height, grid.width), dtype=bool)
    rotation_blocked = np.zeros((grid.height, grid.width), dtype=bool)
    angles = np.arange(headings)*math.tau/headings
    pad = margin + grid.resolution/2
    for layer in mode["layers"]:
        u, v = layer["length"]/2, layer["width"]/2
        radius = math.hypot(u, v)
        for k, a in enumerate(angles):
            ex, ey = abs(math.cos(a))*u+abs(math.sin(a))*v+pad, abs(math.sin(a))*u+abs(math.cos(a))*v+pad
            blocked[k] |= ((grid.x[None,:]-ex < grid.bounds[0]) | (grid.x[None,:]+ex > grid.bounds[2]) |
                           (grid.y[:,None]-ey < grid.bounds[1]) | (grid.y[:,None]+ey > grid.bounds[3]))
        rotation_blocked |= ((grid.x[None,:]-radius-pad < grid.bounds[0]) | (grid.x[None,:]+radius+pad > grid.bounds[2]) |
                             (grid.y[:,None]-radius-pad < grid.bounds[1]) | (grid.y[:,None]+radius+pad > grid.bounds[3]))
        for s in solids:
            # Keep height exact: an isotropic 2-D margin must not erase real vertical underpasses.
            if s["max"][2] <= layer["bottom"] or s["min"][2] >= layer["top"]:
                continue
            lo, hi = np.array(s["min"][:2])-pad, np.array(s["max"][:2])+pad
            centre, half = (lo+hi)/2, (hi-lo)/2
            rows, cols = grid.window(lo-radius, hi+radius)
            dx, dy = grid.x[cols][None,:]-centre[0], grid.y[rows][:,None]-centre[1]
            rotation_blocked[rows,cols] |= np.maximum(np.abs(dx)-half[0],0)**2 + np.maximum(np.abs(dy)-half[1],0)**2 <= radius**2
            for k,a in enumerate(angles):
                c, sn = math.cos(a), math.sin(a)
                ac, ass = abs(c), abs(sn)
                hit = ((np.abs(dx) <= half[0]+ac*u+ass*v) & (np.abs(dy) <= half[1]+ass*u+ac*v) &
                       (np.abs(c*dx+sn*dy) <= u+ac*half[0]+ass*half[1]) &
                       (np.abs(-sn*dx+c*dy) <= v+ass*half[0]+ac*half[1]))
                blocked[k,rows,cols] |= hit
    return blocked, rotation_blocked


def raw_layers(grid, solids):
    occupied = np.zeros((grid.height,grid.width),dtype=bool)
    clearance = np.full((grid.height,grid.width),np.inf,dtype=np.float32)
    for s in solids:
        rows, cols = grid.window(s["min"][:2],s["max"][:2])
        xs, ys = grid.x[cols][None,:], grid.y[rows][:,None]
        hit = ((xs+grid.resolution/2 >= s["min"][0]) & (xs-grid.resolution/2 <= s["max"][0]) &
               (ys+grid.resolution/2 >= s["min"][1]) & (ys-grid.resolution/2 <= s["max"][1]))
        if s["min"][2] < .5 and s["max"][2] > .02:
            occupied[rows,cols] |= hit
        clearance[rows,cols] = np.where(hit,np.minimum(clearance[rows,cols],s["min"][2]),clearance[rows,cols])
    return occupied,clearance
