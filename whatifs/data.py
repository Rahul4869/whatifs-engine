"""whatifs/data.py v7.0 - seed data loaded into the Sheet at setup: topic grids, banned list, strategy pools, director lessons."""
import hashlib, itertools, random

EVERYDAY = ["nail clippings","sneezes","blinks","yawns","hiccups","footsteps","toilet flushes","hair strands","tears","burps",
 "cups of coffee","phone screens","microwaves","fridge doors","car horns","light switches","shower drips","pieces of chewing gum","pencils","paper cuts",
 "eyelashes","fingerprints","heartbeats","shadows","snores","hand claps","whistles","jumps","high-fives","sighs",
 "grains of rice","ice cubes","balloons","sugar cubes","pillows","shoelaces","coins","toothbrushes","sunglasses","umbrellas"]
COLLECTIVE = ["all 8 billion people dropped their {x} into the ocean at the same second","every {x} on Earth happened at exactly the same moment",
 "every {x} on Earth vanished overnight","nobody on Earth made a single one of their {x} for a day","everyone's {x} were collected into one pile",
 "every {x} ever made came back at once","all {x} on Earth doubled in size","every one of the {x} on Earth became magnetic",
 "all {x} on Earth fell upward for ten seconds","all {x} on Earth turned to solid gold","all {x} became as heavy as a car",
 "all {x} on Earth were launched into space","all {x} on Earth glowed in the dark","all {x} made a sound you could hear from orbit",
 "you could only have ten more {x} in your life","all {x} on Earth were teleported to the Moon","all {x} on Earth froze to absolute zero",
 "all {x} became self-aware for one minute","all {x} on Earth were dropped from the edge of space","all {x} on Earth started orbiting your head",
 "everyone made their {x} in perfect sync every second","all {x} on Earth were a thousand degrees hot","all {x} on Earth turned into antimatter",
 "all {x} in history were stacked into one tower","all {x} on Earth started shrinking forever","every one of the {x} was replaced by a tiny black hole",
 "all {x} on Earth became edible","all {x} on Earth popped like firecrackers","your {x} kept multiplying and never stopped","all {x} on Earth arrived at your house"]
STRANGE = ["your skin bacteria","the dust on the Moon","the air in your lungs","the iron in your blood","the water in your body","your stomach acid",
 "the Sun's light","Earth's magnetic field","the Mariana Trench","Saturn's rings","a teaspoon of neutron star","deep-ocean pressure",
 "a single atom","the speed of sound","your nerve signals","your bones","the ozone layer","clouds","a mosquito","an ant colony"]
RULES = ["became 1,000 times stronger","switched off for 60 seconds","could be touched","were the size of a city","landed in your living room",
 "followed you everywhere","worked backwards","became visible","could talk","sped up 100 times",
 "were sold at the supermarket","became your only food","became a national border","turned into honey","got a mind of its own",
 "fit in your pocket","lasted forever","appeared for one second a day","doubled every hour","could be heard"]
BANNED = [("earth stopped spinning","overused"),("earth stops spinning","overused"),("oxygen disappear","overused"),("speed of light meteor","overused"),
 ("meteor at the speed of light","overused"),("asteroid at the speed of light","overused"),("hits jupiter","lame"),("moon disappear","overused"),
 ("sun disappear","overused"),("fell into a black hole","overused"),("gravity disappear","overused"),("earth was flat","overused"),
 ("dinosaurs never","overused"),("sun exploded","overused"),("earth stopped for","overused"),
 ("cure for","policy: medical"),("you should take","policy: advice"),("election","policy: politics"),("president","policy: real person"),("terror","policy: real events")]

def ptype_for(text):
    t = text.lower()
    if any(k in t for k in ["moon","sun","saturn","neutron","space","orbit","black hole","antimatter","magnetic field","ozone"]): return "cosmic"
    if any(k in t for k in ["skin","blood","bones","lungs","stomach","nerve","heart","teeth","body","tears","eyelash","hair","sneez","yawn","hiccup","burp","snore","blink"]): return "body"
    return "collective"

STRATEGIES = {
 "story": {"S1_escalation": "Ordinary moment, then each beat raises scale or stakes; end on the biggest consequence and one human-sized image.",
  "S2_climax_first": "Open on the climax (6-12 s), freeze, ask 'how did we get here?', rewind to the ordinary start, build back, replay the climax with new meaning, then a twist.",
  "S3_countdown": "Clock structure: second 1, minute 1, hour 1, day 1, year 1. Time on screen each beat.",
  "S4_two_timelines": "Two timelines cut together (you in your kitchen / the planet). They collide at the climax.",
  "S5_false_ending": "Apparent resolution at ~70%, viewer relaxes, then the overlooked consequence turns out bigger.",
  "S6_question_chain": "Each answer opens a stranger question. 5-7 linked questions. Final answer loops to the first.",
  "S7_reverse": "Start with the final state of the world, then go back step by step to the tiny cause."},
 "hook": {"O1_second_person": "Put the viewer inside it in the first sentence.", "O2_number_shock": "One specific absurd number in the first 5 seconds.",
  "O3_cold_climax": "Most spectacular frame, no context, one line.", "O4_wrong_assumption": "'You think nothing would happen. You'd be wrong.'",
  "O5_sound_first": "A strange sound in black, then reveal what made it.", "O6_tiny_detail": "Extreme close-up of something ordinary, pull back to reveal scale.",
  "O7_deadline": "A countdown on screen in the first 3 seconds.", "O8_dry_joke": "Deadpan relatable aside, then hard cut to dread."},
 "voice": {"hypnotic": "Slow, low, long pauses.", "urgent": "Faster, short gaps.", "slow_burn": "Starts calm, speeds up.",
  "brake": "Starts fast, slows for the reveal.", "conversational": "Like telling a friend."},
 "reel": {"R1_climax_why": "Climax first, then 'but why?'. Cut to black on the question.", "R2_countdown": "'Second 1... second 10...' stop one step before the answer.",
  "R3_myth": "'Most people think X. They're wrong.' Cut before the answer.", "R4_three_facts": "Three facts, the third held back.",
  "R5_scale_ladder": "Body, then city, then planet. Freeze at planet level."},
 "humour": {"none": "No jokes.", "light": "One dry aside in the cold open and one end callback.", "medium": "Cold-open aside, relief line after the peak, end callback (max 3)."},
 "thumb": {"T1_object_scale": "One ordinary object, enormous, against a dramatic landscape.", "T2_before_after": "Split frame: normal world vs aftermath.",
  "T3_silhouette": "Silhouetted person, rim-lit, facing the impossible scene. No real person.", "T4_number": "One giant number + one tiny object.",
  "T5_question": "Short question in huge type over the climax frame.", "T6_macro": "Extreme macro of something familiar, gone wrong."},
 "title": {"N1_what_if": "What If [specific absurd premise]?", "N2_you": "What If You [did X] for [time]?", "N3_number": "What If 8 Billion People [did X] At Once?",
  "N4_happens": "What Actually Happens If [X]", "N5_wrong": "Everyone Is Wrong About What Happens If [X]"},
}
# ---------------- v7.1: 12 topic families (rotated, learned, 'everyone on Earth' capped) ----------------
FAMILIES = {
 "F01_body": ("Your body", "body", ["your bones","your skin","your blood","your heart","your lungs","your teeth","your eyes","your brain","your stomach","your hair"],
   ["What if {x} turned to glass for 24 hours?","What if {x} became completely see-through?","What if {x} worked twice as fast forever?","What if {x} stopped for exactly ten seconds?",
    "What if {x} glowed every time you lied?","What if {x} grew back brand new every night?","What if {x} were swapped with a stranger's while you slept?","What if {x} ran on sunlight?",
    "What if {x} aged 50 years in one day?","What if {x} could talk back?"]),
 "F02_time": ("Time", "collective", ["one second","your sleep","every Monday","your childhood","the last hour","midnight","your lunch break","sunrise","your future","yesterday"],
   ["What if {x} lasted a full year?","What if you could rewind {x} only once?","What if {x} was erased from everyone's memory?","What if {x} moved ten times slower for you only?",
    "What if you could sell {x}?","What if {x} repeated until you fixed one thing?","What if {x} came with a countdown only you could see?","What if {x} could be stolen?",
    "What if {x} skipped ahead without warning?","What if {x} happened twice in a row?"]),
 "F03_scale": ("Scale", "collective", ["a grain of sand","a single ant","a raindrop","a drop of honey","a snowflake","a mosquito","a coin","a strand of hair","one cell of your body","a teaspoon of water"],
   ["What if {x} weighed as much as a mountain?","What if {x} were the size of New York?","What if {x} were a million degrees hot?","What if {x} moved as fast as a bullet?",
    "What if {x} landed on your tongue at the size of a bus?","What if {x} were dropped from the edge of space?","What if {x} could never be destroyed?","What if {x} became a black hole?",
    "What if {x} doubled every minute?","What if {x} were made of neutron star matter?"]),
 "F04_senses": ("Senses", "body", ["Wi-Fi signals","sound","heat","smells","gravity","ultraviolet light","radio waves","your own heartbeat","magnetic fields","electricity"],
   ["What if you could see {x}?","What if you could taste {x}?","What if you heard {x} all the time?","What if {x} suddenly became painful?","What if you lost the ability to feel {x}?",
    "What if {x} had a colour?","What if {x} were ten times stronger?","What if {x} could be recorded and replayed?","What if only you could sense {x}?","What if {x} switched off for an hour?"]),
 "F05_tech": ("Everyday tech", "collective", ["your phone","the internet","GPS","your earbuds","elevators","traffic lights","the cloud","your smartwatch","satellites","the power grid"],
   ["What if {x} went offline forever at noon?","What if {x} had a million times more power?","What if {x} could read your thoughts?","What if {x} started lying to you?",
    "What if {x} had never been invented?","What if {x} became alive for one hour?","What if {x} only worked when you were happy?","What if {x} leaked everything it ever recorded?",
    "What if {x} became 100 times faster overnight?","What if {x} chose who it worked for?"]),
 "F06_nature": ("Nature", "cosmic", ["trees","the ocean","clouds","rain","volcanoes","rivers","the wind","lightning","coral reefs","mushrooms"],
   ["What if {x} screamed when hurt?","What if {x} could move on their own?","What if {x} stopped for one week?","What if {x} were 1,000 times bigger?","What if {x} turned to glass?",
    "What if {x} became intelligent?","What if {x} appeared in your bedroom?","What if {x} ran backwards?","What if {x} glowed at night?","What if {x} vanished from Earth?"]),
 "F07_places": ("Extreme places", "cosmic", ["the Mariana Trench","Mount Everest","the Sahara","Antarctica","the far side of the Moon","the Amazon","the inside of a volcano","the bottom of Niagara Falls","the edge of space","a hurricane's eye"],
   ["What if you rode a glass elevator to {x}?","What if you had to live in {x} for 30 days?","What if your house were teleported to {x}?","What if {x} were moved next to your city?",
    "What if you woke up in {x}?","What if {x} were your daily commute?","What if you shouted in {x}?","What if you lit a match in {x}?","What if you spent one minute unprotected in {x}?",
    "What if you dropped your phone in {x}?"]),
 "F08_rules": ("Strange rules", "collective", ["colour","friction","shadows","echoes","sleep","reflections","lying","forgetting","gravity","silence"],
   ["What if {x} disappeared for 24 hours?","What if {x} were illegal?","What if {x} cost money?","What if {x} worked backwards?","What if {x} only existed at night?",
    "What if {x} doubled every day?","What if {x} could be bought and sold?","What if {x} happened only to you?","What if {x} switched off for one second?","What if {x} were invented tomorrow?"]),
 "F09_space": ("Space, up close", "cosmic", ["Saturn's rings","the Sun","a comet","the Moon","Mars","a black hole","the International Space Station","Jupiter's Great Red Spot","a neutron star","Venus"],
   ["What if you took a bath in {x}?","What if {x} were in your backyard?","What if you touched {x} for one second?","What if {x} made a sound we could hear?","What if {x} were the size of a car?",
    "What if you swapped places with {x} for a day?","What if {x} showed up in tonight's sky?","What if {x} followed Earth like a pet?","What if {x} were for sale?","What if {x} were made of candy?"]),
 "F10_food": ("Food and chemistry", "body", ["chewing gum","coffee","chili peppers","salt","sugar","honey","popcorn","ice cream","bread","tap water"],
   ["What if you chewed {x} for 30 days straight?","What if {x} were the only thing you could eat?","What if {x} were a million times stronger?","What if {x} exploded when heated?",
    "What if {x} disappeared from Earth?","What if your body made {x}?","What if {x} cost more than gold?","What if {x} froze instantly in your mouth?","What if a lake were made of {x}?",
    "What if {x} became addictive overnight?"]),
 "F11_future": ("Future tech", "collective", ["your memories","your face","your voice","your dreams","your DNA","your heartbeat","your thoughts","your shadow","your personality","your sleep"],
   ["What if {x} were backed up to the cloud and hacked?","What if {x} could be rented out?","What if {x} were copied by a stranger?","What if {x} could be edited like a photo?",
    "What if {x} were sold at auction?","What if {x} were streamed live?","What if {x} were deleted by mistake?","What if {x} needed a monthly subscription?","What if {x} were owned by a company?",
    "What if {x} got an update you didn't want?"]),
 "F12_everyone": ("Everyone on Earth", "collective", EVERYDAY[:12], [("What if " + c + "?") for c in COLLECTIVE[:10]]),
}
FAMILY_PTYPE = {k: v[1] for k, v in FAMILIES.items()}
FAMILY_PLAYLIST = {k: "What If: " + v[0] for k, v in FAMILIES.items()}
STRATEGIES["family"] = {k: v[0] for k, v in FAMILIES.items()}
STRATEGIES["title"]["N6_statement"] = "Statement + consequence, no question mark: 'Your Bones Are Glass Now. Don't Sneeze.'"

AI_TELLS = ["delve", "tapestry", "in this video", "let's dive", "dive in", "buckle up", "imagine a world", "fascinating", "it's important to note",
            "in conclusion", "embark", "journey", "unleash", "realm", "testament to", "intricate", "moreover", "furthermore", "whether you're",
            "stay tuned", "mind-blowing", "game-changer", "here's the thing", "let that sink in", "ever wondered", "in today's", "plethora", "navigate the"]

def premise_rows():
    rows = []
    for fam, (label, ptype, anchors, templates) in FAMILIES.items():
        for x, t in itertools.product(anchors, templates):
            p = t.format(x=x) if "{x}" in t else t
            rows.append({"premise_id": fam[:3] + hashlib.md5(p.encode()).hexdigest()[:7].upper(), "grid": fam, "anchor": x, "rule": t[:60],
                         "lens": label, "premise": p, "ptype": ptype, "status": "FRESH", "episode_id": "", "used_at": ""})
    seen, out = set(), []
    for r in rows:
        if r["premise"] not in seen: seen.add(r["premise"]); out.append(r)
    random.Random(7).shuffle(out); return out

def strategy_rows():
    return [{"dimension": d, "name": n, "definition": t, "status": "ACTIVE", "plays": 0, "score_sum": 0, "score_n": 0, "created": "seed", "source": "seed"}
            for d, items in STRATEGIES.items() for n, t in items.items()]

DIRECTORS = """Craft lessons (learn the technique, never copy a scene):
Hitchcock - show the bomb under the table before the character knows. Nolan - converging timelines, ticking clock.
Villeneuve - scale through silence; tiny human vs vast structure. Spielberg - show the effect before the monster (the water ripple).
Fincher - precise unsettling detail. Kubrick - symmetry, slow push-ins. Cuaron - long unbroken dread.
Bong Joon-ho - dry laugh then sudden horror. Edgar Wright - cuts on sound, visual punchlines, callbacks. Jordan Peele - comedy timing used for fear.
Rod Serling - ordinary premise, ironic last turn. Sagan/Attenborough - one intimate human sentence after the huge number.
Kurzgesagt/Vsauce - every answer opens a better question. MrBeast packaging - title and thumbnail promise one clear impossible image."""
