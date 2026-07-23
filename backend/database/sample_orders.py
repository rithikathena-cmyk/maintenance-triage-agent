"""A curated pool of 50 distinct sample work orders for the manual dispatcher.

The "Generate next batch of orders" button pages through this list in chunks
(see ``BATCH_SIZE``): each press inserts the next set and triages them into
reviewable proposals. Titles are unique so every insert is genuinely new.

The mix is deliberate — injury-risk orders (the safety guard force-escalates
these to safety-critical), production-stopping breakdowns, and routine/cosmetic
issues — so the queue shows the full range of urgencies.
"""

# How many orders each button press reveals.
BATCH_SIZE = 10

SAMPLE_ORDERS = [
    # ------------------------------------------------------------------ Set 1
    {
        "title": "Hydraulic press #7 ram drifts down on its own",
        "description": "Press #7 ram creeps downward when idle with no one at the controls. An operator could have a hand in the die — serious crush and pinch-point injury risk.",
        "location": "Line A - Press #7",
        "reported_by": "operator.j.rivera",
    },
    {
        "title": "Missing chain guard on packaging drive sprocket",
        "description": "The guard over the drive sprocket and chain on Packaging Line 2 is gone. Exposed rotating chain right at hand height — entanglement and amputation hazard.",
        "location": "Packaging Line 2",
        "reported_by": "operator.d.okafor",
    },
    {
        "title": "CNC lathe #3 spindle drive faults under load",
        "description": "Lathe #3 throws a spindle drive fault whenever it takes a cut, so no parts can run. Machine is down but in a safe state.",
        "location": "Cell 6 - CNC Lathe #3",
        "reported_by": "operator.m.chen",
    },
    {
        "title": "Injection molder #2 won't hold barrel temperature",
        "description": "Molder #2 keeps dropping below set point and can't maintain barrel temp, so the line is stopped. No hazard.",
        "location": "Molding - Machine 2",
        "reported_by": "operator.r.singh",
    },
    {
        "title": "Main line conveyor VFD tripped on Line B",
        "description": "The main conveyor variable-frequency drive tripped and won't reset; Line B is halted. Stopped safely, nobody at risk.",
        "location": "Line B - Main Conveyor",
        "reported_by": "operator.s.patel",
    },
    {
        "title": "HMI screen dim on batch mixer #4",
        "description": "The HMI backlight on mixer #4 is very dim and hard to read in daylight. Mixer still runs fine.",
        "location": "Batching - Mixer #4",
        "reported_by": "operator.l.gomez",
    },
    {
        "title": "Intermittent flicker on Cell 3 stack light",
        "description": "The green stack light on Cell 3 flickers on and off. Cosmetic; the cell operates normally.",
        "location": "Cell 3",
        "reported_by": "operator.t.nguyen",
    },
    {
        "title": "Exposed 480V busbar in open drive panel",
        "description": "A cover is missing on the drive panel in Substation B, leaving an energized 480V busbar exposed. Arc-flash and electric-shock risk to anyone nearby.",
        "location": "Substation B",
        "reported_by": "operator.b.lindqvist",
    },
    {
        "title": "Palletizer robot in fault, won't home",
        "description": "The palletizer robot at End of Line 1 faulted and won't return to home, so palletizing is stopped. Robot is stationary and safe.",
        "location": "End of Line 1 - Palletizer",
        "reported_by": "operator.k.abara",
    },
    {
        "title": "Slow coolant weep at CNC #4 fitting",
        "description": "A fitting on the CNC #4 coolant line weeps slowly into the tray. Contained, not a hazard, just a nuisance.",
        "location": "Cell 3 - CNC #4",
        "reported_by": "operator.m.chen",
    },

    # ------------------------------------------------------------------ Set 2
    {
        "title": "Ammonia smell near refrigeration unit",
        "description": "Strong ammonia odor around the cold-store refrigeration skid; a tech felt lightheaded. Possible refrigerant leak — toxic-exposure hazard, ventilate and isolate.",
        "location": "Cold Store - Refrigeration Skid",
        "reported_by": "operator.n.acosta",
    },
    {
        "title": "Overhead crane pendant sticks in 'up'",
        "description": "The Bay 4 crane pendant sometimes keeps hoisting after the button is released. A load could be raised into the structure or drop — struck-by injury risk below.",
        "location": "Bay 4 - Overhead Crane",
        "reported_by": "operator.p.osei",
    },
    {
        "title": "CNC mill #5 tool changer jammed",
        "description": "The automatic tool changer on mill #5 is jammed mid-swap, so the machine is down. No danger, just idle.",
        "location": "Cell 7 - CNC Mill #5",
        "reported_by": "operator.a.varga",
    },
    {
        "title": "Chiller for Line C down, temp climbing",
        "description": "The process chiller serving Line C has stopped and coolant temperature is rising; the line will have to stop soon. No injury risk.",
        "location": "Utilities - Chiller 2",
        "reported_by": "operator.f.moreau",
    },
    {
        "title": "Labeler PLC comms fault on Packaging Line 1",
        "description": "The labeler PLC keeps dropping communication and the line faults out. Packaging stopped; safe state.",
        "location": "Packaging Line 1 - Labeler",
        "reported_by": "operator.y.kim",
    },
    {
        "title": "Squeal from idler bearing at low speed",
        "description": "A conveyor idler on Line B squeals at low speed. Still running within spec; worth checking the bearing eventually.",
        "location": "Line B - Idler",
        "reported_by": "operator.s.patel",
    },
    {
        "title": "Grinding wheel wobbles badly at speed",
        "description": "The wheel on Toolroom Grinder 2 wobbles and vibrates hard at full speed. Risk of the wheel shattering and throwing fragments — laceration/eye-injury hazard.",
        "location": "Toolroom - Grinder 2",
        "reported_by": "operator.h.tanaka",
    },
    {
        "title": "Vacuum pump lost seal, no vacuum on laminator",
        "description": "The lamination vacuum pump lost its seal and can't pull vacuum, so lamination is stopped. Not hazardous.",
        "location": "Lamination - Vacuum Pump",
        "reported_by": "operator.c.dubois",
    },
    {
        "title": "Worn anti-fatigue mat at pack bench",
        "description": "The anti-fatigue mat at the packing bench is curling at the edge. Minor trip point but low risk; replace when convenient.",
        "location": "Packaging - Pack Bench",
        "reported_by": "operator.l.gomez",
    },
    {
        "title": "Faded lockout label on disconnect 12",
        "description": "The lockout/tagout label on disconnect 12 in Cell 5 has faded and is hard to read. Cosmetic; the disconnect works.",
        "location": "Cell 5 - Disconnect 12",
        "reported_by": "operator.b.lindqvist",
    },

    # ------------------------------------------------------------------ Set 3
    {
        "title": "Forklift #6 horn and brakes intermittent",
        "description": "Forklift #6's horn and brakes both work only intermittently; it nearly failed to stop at a pedestrian aisle. Someone could be struck — take it out of service.",
        "location": "Warehouse - Forklift 6",
        "reported_by": "operator.c.dubois",
    },
    {
        "title": "Robot cell light curtain bypassed",
        "description": "The safety light curtain on Weld Cell 5 has been jumpered out so the robot runs with the gate open. No protection from the moving arm — serious injury risk.",
        "location": "Weld Cell 5",
        "reported_by": "operator.k.abara",
    },
    {
        "title": "Welder wire feeder stalls mid-weld",
        "description": "The wire feeder on Weld Cell 2 stalls partway through a weld, scrapping the part. Machine down; no hazard.",
        "location": "Weld Cell 2 - Wire Feeder",
        "reported_by": "operator.k.abara",
    },
    {
        "title": "Hydraulic power unit low-pressure fault",
        "description": "The press-shop HPU keeps faulting on low pressure and won't build up, so the presses can't cycle. Safe, just no output.",
        "location": "Press Shop - HPU",
        "reported_by": "operator.j.rivera",
    },
    {
        "title": "Dust collector motor overload trips",
        "description": "The finishing dust collector motor trips on overload after a few minutes; without it, finishing has to stop for air quality. No immediate injury.",
        "location": "Finishing - Dust Collector",
        "reported_by": "operator.n.acosta",
    },
    {
        "title": "Sticky pushbutton on Line A operator panel",
        "description": "The cycle-start pushbutton on the Line A panel sticks and needs a firm press. Line runs fine; minor annoyance.",
        "location": "Line A - Operator Panel",
        "reported_by": "operator.s.patel",
    },
    {
        "title": "Steam line lagging stripped, pipe exposed",
        "description": "A section of insulation is missing on the boiler-room steam line, leaving bare hot pipe at shoulder height. Contact-burn hazard for anyone passing.",
        "location": "Boiler Room - Steam Line",
        "reported_by": "operator.f.moreau",
    },
    {
        "title": "Servo axis following error on router 1",
        "description": "The X axis on Router 1 throws a following error and stops the program. Machine is down; safe state.",
        "location": "Router 1",
        "reported_by": "operator.a.varga",
    },
    {
        "title": "Minor air leak at clamp fitting",
        "description": "A pneumatic fitting on an assembly clamp hisses slightly. Clamp still holds; schedule a reseal.",
        "location": "Assembly - Clamp Station",
        "reported_by": "operator.t.nguyen",
    },
    {
        "title": "Loose access-panel screw on Cell 6 guard",
        "description": "One retaining screw on the Cell 6 guard panel is loose. Guard is still secure by the others; tighten when convenient.",
        "location": "Cell 6",
        "reported_by": "operator.m.chen",
    },

    # ------------------------------------------------------------------ Set 4
    {
        "title": "Oil spill spreading across main walkway",
        "description": "Hydraulic oil is spreading across the main assembly walkway from a leaking unit. Large slip hazard — someone could fall; barrier off and clean up.",
        "location": "Assembly Aisle 3",
        "reported_by": "operator.d.okafor",
    },
    {
        "title": "Guard interlock defeated on sheet-metal shear",
        "description": "The interlock on the shear guard has been taped down so it runs with the guard up. The blade can cycle with hands in reach — amputation hazard.",
        "location": "Sheet Metal - Shear",
        "reported_by": "operator.h.tanaka",
    },
    {
        "title": "Boiler feed pump cavitating",
        "description": "The boiler feed pump is cavitating and losing prime; if it fails the boiler trips and shuts the plant steam. Not an injury risk right now.",
        "location": "Boiler Room - Feed Pump",
        "reported_by": "operator.f.moreau",
    },
    {
        "title": "Conveyor gearbox seized on incline",
        "description": "The incline conveyor gearbox on Line A has seized and the belt won't move, halting Line A. Belt is stopped and safe.",
        "location": "Line A - Incline Conveyor",
        "reported_by": "operator.s.patel",
    },
    {
        "title": "Barcode scanner offline at pack station",
        "description": "The fixed barcode scanner at the shipping pack station is offline, so orders can't be verified and packing is blocked. No hazard.",
        "location": "Shipping - Pack Station",
        "reported_by": "operator.y.kim",
    },
    {
        "title": "Fan rattle in control cabinet",
        "description": "The cooling fan in the electrical-room control cabinet rattles. Still moving air; replace the fan at next PM.",
        "location": "Electrical Room - Control Cabinet",
        "reported_by": "operator.b.lindqvist",
    },
    {
        "title": "Compressed gas cylinder unsecured and tipping",
        "description": "A full argon cylinder in the gas store is off its chain and leaning. If it falls and the valve shears it becomes a projectile — serious struck-by hazard.",
        "location": "Gas Store",
        "reported_by": "operator.k.abara",
    },
    {
        "title": "Air dryer bypassed, moisture in air lines",
        "description": "The compressed-air dryer is bypassed and moisture is reaching the tools, causing intermittent faults across the shop. No injury risk.",
        "location": "Compressor Room - Air Dryer",
        "reported_by": "operator.f.moreau",
    },
    {
        "title": "Peeling floor tape near Cell 2",
        "description": "The yellow aisle tape by Cell 2 is peeling up. Aisle is still clearly marked; re-tape when convenient.",
        "location": "Cell 2",
        "reported_by": "operator.d.okafor",
    },
    {
        "title": "Dust build-up on Line C photo-eye sensor",
        "description": "Dust on the Line C photo-eye causes the occasional false trigger. Line recovers on its own; clean the lens.",
        "location": "Line C - Photo-eye",
        "reported_by": "operator.t.nguyen",
    },

    # ------------------------------------------------------------------ Set 5
    {
        "title": "Stamping press clutch slow to engage",
        "description": "The clutch on Stamping 1 is slow to engage and the ram hesitates before dropping. Unpredictable ram motion is a pinch/crush hazard — lock it out.",
        "location": "Stamping 1",
        "reported_by": "operator.j.rivera",
    },
    {
        "title": "Cooling tower fan belt snapped",
        "description": "The cooling-tower fan belt snapped, so tower capacity is down and process cooling is dropping across the plant. No immediate injury.",
        "location": "Utilities Roof - Cooling Tower",
        "reported_by": "operator.f.moreau",
    },
    {
        "title": "Wobbly caster on parts cart",
        "description": "One caster on a toolroom parts cart wobbles and drags. Cart still usable; swap the caster.",
        "location": "Toolroom",
        "reported_by": "operator.l.gomez",
    },
    {
        "title": "Drip tray full under press #3",
        "description": "The drip tray under press #3 is nearly full of oil and should be emptied before it overflows. Contained for now; routine.",
        "location": "Press Shop - Press #3",
        "reported_by": "operator.j.rivera",
    },
    {
        "title": "Legend plate missing on selector switch",
        "description": "The legend plate labeling a selector switch on the Line B panel is missing. Switch works; operators know it, but label it for clarity.",
        "location": "Line B - Panel",
        "reported_by": "operator.s.patel",
    },
    {
        "title": "Scuffed lens on machine work light",
        "description": "The work-light lens on Cell 7 is scuffed and dims the light. Cosmetic; replace the lens.",
        "location": "Cell 7",
        "reported_by": "operator.a.varga",
    },
    {
        "title": "Slow-draining sink in wash bay",
        "description": "The parts-wash sink drains slowly and backs up. Housekeeping issue, no hazard; snake the drain.",
        "location": "Wash Bay",
        "reported_by": "operator.c.dubois",
    },
    {
        "title": "Creaking hinge on cell access door",
        "description": "The access door on Weld Cell 5 creaks and drags on its hinge. Door still closes and interlocks; lubricate the hinge.",
        "location": "Weld Cell 5 - Access Door",
        "reported_by": "operator.k.abara",
    },
    {
        "title": "Thermostat reads high in office area",
        "description": "The front-office thermostat reads several degrees high and the area is warm. Comfort issue only; check the HVAC.",
        "location": "Front Office",
        "reported_by": "operator.l.gomez",
    },
    {
        "title": "Label printer low-quality print",
        "description": "The shipping label printer prints faint, streaky labels that sometimes won't scan. Slows shipping; clean the head or replace the ribbon.",
        "location": "Shipping - Label Printer",
        "reported_by": "operator.y.kim",
    },
]
