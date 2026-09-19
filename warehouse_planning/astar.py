"""Reference A*: pose states, eight headings, forward/reverse and guarded turns.

No lateral moves: an (x,y)-only A* would lose essential slot alignment information.
It returns a geometric path, not timing, wheel commands, or a mission controller.
"""
import heapq
import itertools
import math
import time


class PlanningError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class SearchBudgetExceeded(RuntimeError):
    code = "SEARCH_BUDGET_EXCEEDED"

DIRECTIONS=((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1))


def heading(yaw):
    return round(yaw/(math.pi/4)) % 8


def plan(grid, blocked, rotation_blocked, start, goal, max_expansions=1500000,
         reverse_multiplier=1.1, turn_cost=.18, use_heuristic=True, on_expand=None):
    started=time.perf_counter()
    if blocked.shape!=(8,grid.height,grid.width) or rotation_blocked.shape!=(grid.height,grid.width):
        raise PlanningError("INVALID_MAP","invalid map array shape")
    if blocked.dtype.kind!='b' or rotation_blocked.dtype.kind!='b':
        raise PlanningError("INVALID_MAP","maps must contain boolean blocked values")
    if max_expansions<0 or not math.isfinite(reverse_multiplier) or reverse_multiplier<1 or not math.isfinite(turn_cost) or turn_cost<=0:
        raise PlanningError("INVALID_COST","reverse multiplier must be >=1 and turn cost positive")
    def state(p):
        if len(p)!=3 or not all(math.isfinite(v) for v in p):raise PlanningError("INVALID_POSE","pose must contain finite x,y,yaw")
        h=heading(p[2])
        if abs((p[2]-h*math.pi/4+math.pi)%math.tau-math.pi)>.001:
            raise PlanningError("UNSUPPORTED_HEADING","planner requires yaw at a 45-degree heading")
        try:c,r=grid.cell(*p[:2])
        except ValueError as exc:raise PlanningError("OUT_OF_BOUNDS",str(exc)) from exc
        return c,r,h
    source,target=state(start),state(goal)
    for label,s in (("start",source),("goal",target)):
        if blocked[s[2],s[1],s[0]]:
            raise PlanningError(label.upper()+"_BLOCKED",label+" is blocked for this mode/heading")
    def heuristic(s):
        dx,dy=abs(s[0]-target[0]),abs(s[1]-target[1])
        return (max(dx,dy)+(math.sqrt(2)-1)*min(dx,dy))*grid.resolution if use_heuristic else 0.
    serial=itertools.count(); queue=[(heuristic(source),next(serial),0.,source)]
    costs={source:0.}; parent={}; expansions=0
    while queue:
        _,_,g,s=heapq.heappop(queue)
        if g!=costs[s]: continue
        if s==target:
            states=[s]
            while s in parent: s=parent[s];states.append(s)
            states.reverse()
            poses=[[*grid.world(c,r),h*math.pi/4] for c,r,h in states]
            segments=[];distance=0.;reverse_distance=0.;turns=0
            for a,b in zip(poses,poses[1:]):
                length=math.hypot(b[0]-a[0],b[1]-a[1])
                if length==0:
                    da=(b[2]-a[2]+math.pi)%math.tau-math.pi
                    action="turn_left" if da>0 else "turn_right";turns+=1
                else:
                    action="forward" if (b[0]-a[0])*math.cos(a[2])+(b[1]-a[1])*math.sin(a[2])>0 else "reverse"
                    distance+=length
                    if action=="reverse":reverse_distance+=length
                if length>0 and segments and segments[-1]["action"]==action and abs(segments[-1]["end"][2]-b[2])<1e-6:
                    segments[-1]["end"]=b;segments[-1]["length_m"]+=length
                else:segments.append({"action":action,"start":a,"end":b,"length_m":length})
            return {"status":"SUCCESS","states":states,"poses":poses,"segments":segments,
                    "cost":g,"length_m":distance,"reverse_length_m":reverse_distance,"turn_steps":turns,
                    "elapsed_s":time.perf_counter()-started,"expansions":expansions}
        expansions+=1
        if expansions>max_expansions: raise SearchBudgetExceeded("A* expansion budget exhausted")
        if on_expand is not None:
            on_expand(s, g, heuristic(s), expansions)
        c,r,h=s; dx,dy=DIRECTIONS[h]; successors=[]
        for sign in (1,-1):
            nc,nr=c+sign*dx,r+sign*dy
            if not (0<=nc<grid.width and 0<=nr<grid.height) or blocked[h,nr,nc]: continue
            if dx and dy and (blocked[h,r,nc] or blocked[h,nr,c]): continue
            successors.append(((nc,nr,h),math.hypot(dx,dy)*grid.resolution*(1 if sign==1 else reverse_multiplier)))
        if not rotation_blocked[r,c]:
            for dh in (-1,1):
                nh=(h+dh)%8
                if not blocked[nh,r,c]: successors.append(((c,r,nh),turn_cost))
        for nxt,cost in successors:
            ng=g+cost
            if ng < costs.get(nxt,math.inf):
                costs[nxt]=ng;parent[nxt]=s
                heapq.heappush(queue,(ng+heuristic(nxt),next(serial),ng,nxt))
    raise PlanningError("UNREACHABLE","goal unreachable")
