"""Converter from blocks JSON format to Zwift ZWO XML format.

This exporter only supports running and cycling workouts.
"""
import re
from typing import List, Optional, Tuple
from xml.etree.ElementTree import Element, SubElement, tostring
from backend.adapters.zwo_schemas import Workout, Step, Target
from backend.adapters.blocks_to_hyrox_yaml import extract_rounds


def extract_power_target(ex_name: str) -> Optional[Target]:
    """Extract power target from exercise name (FTP percentages, watt ranges, etc.).
    
    Examples:
        "50% FTP" -> Target(type="power", min=0.50, max=0.50)
        "103% FTP" -> Target(type="power", min=1.03, max=1.03)
        "85-95% FTP" -> Target(type="power", min=0.85, max=0.95)
        "200-250W" -> Target(type="power", min=0.80, max=1.00)  # approximate if FTP unknown
    
    Returns None if no power target found.
    """
    ex_name_lower = ex_name.lower()
    
    # Pattern 1: Single FTP percentage (e.g., "50% FTP", "103% FTP")
    ftp_match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*ftp', ex_name_lower)
    if ftp_match:
        pct = float(ftp_match.group(1)) / 100.0
        return Target(type="power", min=pct, max=pct)
    
    # Pattern 2: FTP percentage range (e.g., "85-95% FTP", "88–95% FTP")
    ftp_range_match = re.search(r'(\d+(?:\.\d+)?)\s*[–-]\s*(\d+(?:\.\d+)?)\s*%\s*ftp', ex_name_lower)
    if ftp_range_match:
        min_pct = float(ftp_range_match.group(1)) / 100.0
        max_pct = float(ftp_range_match.group(2)) / 100.0
        return Target(type="power", min=min_pct, max=max_pct)
    
    # Pattern 3: Watt range (e.g., "200-250W", "200-250 watts")
    watt_match = re.search(r'(\d+)\s*[–-]\s*(\d+)\s*w', ex_name_lower)
    if watt_match:
        # Approximate: assume 250W is roughly FTP, so convert to percentage
        # This is a rough estimate - ideally we'd have user's FTP
        min_watt = float(watt_match.group(1))
        max_watt = float(watt_match.group(2))
        estimated_ftp = 250.0  # Default assumption
        min_pct = min_watt / estimated_ftp
        max_pct = max_watt / estimated_ftp
        return Target(type="power", min=min_pct, max=max_pct)
    
    # Pattern 4: Single watt value (e.g., "200W")
    single_watt_match = re.search(r'(\d+)\s*w(?!\s*[–-])', ex_name_lower)
    if single_watt_match:
        watt = float(single_watt_match.group(1))
        estimated_ftp = 250.0
        pct = watt / estimated_ftp
        return Target(type="power", min=pct, max=pct)
    
    return None


def _add_text(parent, tag: str, text: str):
    """Helper to add text element to XML."""
    el = SubElement(parent, tag)
    el.text = str(text)
    return el


def _duration_seconds(s: Step) -> int:
    """Calculate duration in seconds for a step."""
    if s.duration_s:
        return s.duration_s
    if s.kind == "interval" and s.reps and s.work_s and s.rest_s:
        return s.reps * (s.work_s + s.rest_s)
    if s.distance_m:
        # Heuristic: ~60s per 200m (~5:00/km pace). Adjust later if you track user threshold.
        return int(max(30, round(s.distance_m * 0.30)))
    return 60


def _avg_scalar(target: Target) -> float:
    """Calculate average scalar from target min/max."""
    if target and target.min is not None and target.max is not None:
        return max(0.10, min(1.50, (target.min + target.max) / 2.0))
    return 0.70  # default endurance


def _hr_to_proxy(scalar: float) -> float:
    """Map HR scalar to power/pace proxy."""
    # crude mapping: %HRR → %FTP proxy (tunable)
    return max(0.5, min(1.1, 0.8 * scalar))


def _rpe_to_proxy(scalar: float) -> float:
    """Map RPE scalar to power/pace proxy."""
    # if RPE was provided on 0–1 scale; if on 1–10, pre-normalize before calling
    return max(0.5, min(1.1, scalar))


def _set_intensity(el, sport: str, on: bool, value: float):
    """Set intensity attribute on XML element.
    
    Note: For Power, convert to percentage (0-100) for Zwift ZWO format.
    """
    if sport == "run":
        el.set("Pace" if on else "OffPace", f"{value:.2f}")
    else:
        # Convert to percentage for Power
        power_pct = int(round(value * 100))
        el.set("Power" if on else "OffPower", str(power_pct))


def _apply_target(el, s: Step, steady: bool, sport: str = "run"):
    """Apply target intensity to XML element.
    
    Note: Zwift ZWO format uses percentages (0-100) for Power, not decimals.
    So 0.50 (50% FTP) should be formatted as "50", not "0.50".
    """
    t = s.target.type if s.target else "none"
    val = _avg_scalar(s.target)

    if t == "power":
        # Convert to percentage (0-100) for Zwift ZWO format
        power_pct = int(round(val * 100))
        if steady:
            el.set("Power", str(power_pct))
        else:
            el.set("OnPower", str(power_pct))
            el.set("OffPower", "40")  # 40% for rest
    elif t == "pace":
        # For RUN: Zwift accepts Pace scalars where 1.00 = threshold pace/speed.
        if sport == "run":
            key = "Pace" if steady else "OnPace"
            el.set(key, f"{val:.2f}")
            if not steady:
                el.set("OffPace", "0.90")
        else:
            # For bike, convert pace to power proxy (as percentage)
            power_pct = int(round(val * 100))
            if steady:
                el.set("Power", str(power_pct))
            else:
                el.set("OnPower", str(power_pct))
                el.set("OffPower", "40")
    elif t == "hr":
        # HR: optional; Zwift de-emphasizes HR targets. Use Power/Pace proxy if needed.
        proxy = _hr_to_proxy(val)
        if sport == "run":
            if steady:
                el.set("Pace", f"{proxy:.2f}")
            else:
                el.set("OnPace", f"{proxy:.2f}")
                el.set("OffPace", "0.90")
        else:
            power_pct = int(round(proxy * 100))
            if steady:
                el.set("Power", str(power_pct))
            else:
                el.set("OnPower", str(power_pct))
                el.set("OffPower", "40")
    elif t == "rpe":
        proxy = _rpe_to_proxy(val)
        if sport == "run":
            if steady:
                el.set("Pace", f"{proxy:.2f}")
            else:
                el.set("OnPace", f"{proxy:.2f}")
                el.set("OffPace", "0.90")
        else:
            power_pct = int(round(proxy * 100))
            if steady:
                el.set("Power", str(power_pct))
            else:
                el.set("OnPower", str(power_pct))
                el.set("OffPower", "40")
    else:
        # No target → aerobic default
        if sport == "run":
            if steady:
                el.set("Pace", "0.70")
            else:
                el.set("OnPace", "0.80")
                el.set("OffPace", "0.90")
        else:
            # Default to 70% FTP for steady, 80% for intervals
            if steady:
                el.set("Power", "70")
            else:
                el.set("OnPower", "80")
                el.set("OffPower", "50")


def block_to_steps(block: dict, sport: str) -> List[Step]:
    """Convert a block to ZWO steps."""
    steps: List[Step] = []
    structure = block.get("structure", "")
    rounds = extract_rounds(structure) if structure else 1
    rest_between_sec = block.get("rest_between_sec")
    time_work_sec = block.get("time_work_sec")
    block_label = block.get("label", "").lower()

    # Check if this is a warmup/cooldown block
    is_warmup = "warmup" in block_label or "primer" in block_label
    is_cooldown = "cooldown" in block_label or "finisher" in block_label

    exercises = block.get("exercises", [])
    
    # Handle blocks with structured exercises (like warmup with multiple steps)
    # Check if we have multiple exercises that should be sequential
    if len(exercises) > 1 and not time_work_sec:
        # Process each exercise as a separate step (only if no time_work_sec on block level)
        for ex in exercises:
            ex_name = ex.get("name", "")
            duration_sec = ex.get("duration_sec")
            # Only use time_work_sec as fallback if exercise has no duration
            if not duration_sec and time_work_sec:
                duration_sec = time_work_sec
            rest_sec = ex.get("rest_sec") or rest_between_sec
            
            # Extract power target from name
            target = extract_power_target(ex_name) or Target()
            
            # Skip exercises without duration (they're just descriptions)
            if duration_sec:
                step = Step(
                    kind="warmup" if is_warmup else "cooldown" if is_cooldown else "steady",
                    duration_s=duration_sec,
                    target=target
                )
                steps.append(step)
                
                # Add rest if specified
                if rest_sec:
                    rest_step = Step(
                        kind="rest",
                        duration_s=rest_sec,
                        target=Target()
                    )
                    steps.append(rest_step)
        
        if steps:
            return steps
    
    # Handle time-based interval blocks (like "60s on, 90s off x3")
    if time_work_sec:
        if exercises:
            ex = exercises[0]
            ex_name = ex.get("name", "")
            duration_sec = ex.get("duration_sec") or time_work_sec
            rest_sec = ex.get("rest_sec") or rest_between_sec
            sets = ex.get("sets") or rounds
            
            # Extract power target from name
            target = extract_power_target(ex_name) or Target()

            # Check if we have multiple exercises that should form a repeating sequence
            if len(exercises) > 1:
                # Multiple exercises that form a sequence (possibly repeating)
                interval_steps: List[Step] = []
                for ex_item in exercises:
                    ex_item_name = ex_item.get("name", "")
                    ex_item_duration = ex_item.get("duration_sec")
                    # Don't use time_work_sec as fallback here - each exercise should have its own duration
                    if not ex_item_duration:
                        continue  # Skip exercises without explicit duration
                    ex_item_target = extract_power_target(ex_item_name) or target
                    
                    interval_steps.append(Step(
                        kind="steady",
                        duration_s=ex_item_duration,
                        target=ex_item_target
                    ))
                
                # If we have rounds > 1, repeat the sequence
                if rounds > 1 and interval_steps:
                    for round_num in range(rounds):
                        steps.extend(interval_steps)
                        # Add rest between rounds (but not after the last round)
                        if round_num < rounds - 1 and rest_between_sec:
                            steps.append(Step(
                                kind="rest",
                                duration_s=rest_between_sec,
                                target=Target()
                            ))
                elif interval_steps:
                    # Single sequence, no repeats
                    steps.extend(interval_steps)
                elif not interval_steps and time_work_sec:
                    # No exercises with durations, but we have block-level time - use that
                    # Extract target from first exercise name if available
                    if exercises:
                        first_ex_name = exercises[0].get("name", "")
                        recovery_target = extract_power_target(first_ex_name) or target
                    else:
                        recovery_target = target
                    
                    step = Step(
                        kind="warmup" if is_warmup else "cooldown" if is_cooldown else "steady",
                        duration_s=time_work_sec,
                        target=recovery_target
                    )
                    steps.append(step)
            elif sets > 1 and rest_sec:
                # Single exercise that repeats as intervals
                step = Step(
                    kind="interval",
                    work_s=duration_sec,
                    rest_s=rest_sec,
                    reps=sets,
                    target=target
                )
                steps.append(step)
            else:
                # Single steady state
                step = Step(
                    kind="warmup" if is_warmup else "cooldown" if is_cooldown else "steady",
                    duration_s=duration_sec,
                    target=target
                )
                steps.append(step)
        else:
            # Block has time but no exercises with durations - treat as warmup/cooldown
            # Check if any exercises have descriptions but no durations (like "60% FTP easy spin")
            has_description_only = False
            recovery_target = Target()
            if exercises:
                # Check if we can extract a target from the exercise name
                for ex in exercises:
                    ex_name = ex.get("name", "")
                    if ex_name and not ex.get("duration_sec"):
                        recovery_target = extract_power_target(ex_name) or Target()
                        has_description_only = True
                        break
            
            step = Step(
                kind="warmup" if is_warmup else "cooldown" if is_cooldown else "steady",
                duration_s=time_work_sec,
                target=recovery_target
            )
            steps.append(step)
        
        if steps:
            return steps

    # Handle distance-based exercises (running/cycling)
    for ex in block.get("exercises", []):
        ex_name = ex.get("name", "")
        ex_name_lower = ex_name.lower()
        distance_m = ex.get("distance_m")
        distance_range = ex.get("distance_range")
        duration_sec = ex.get("duration_sec")
        rest_sec = ex.get("rest_sec")
        sets = ex.get("sets") or rounds

        # Extract power/pace target from name
        target = extract_power_target(ex_name) or Target()

        # Check if this is a running/cycling exercise
        is_cardio = any(keyword in ex_name_lower for keyword in [
            "run", "jog", "sprint", "pace", "tempo", "easy", "recovery",
            "bike", "ride", "cycle", "spin", "watt", "ftp", "threshold"
        ])

        if distance_m:
            if sets > 1 and rest_sec:
                # Interval repeats with distance
                for _ in range(sets):
                    step = Step(
                        kind="interval",
                        distance_m=distance_m,
                        work_s=None,  # Distance-based, no explicit work time
                        rest_s=rest_sec,
                        reps=1,
                        target=target
                    )
                    steps.append(step)
                    if rest_sec:
                        rest_step = Step(
                            kind="rest",
                            duration_s=rest_sec,
                            target=Target()
                        )
                        steps.append(rest_step)
            else:
                # Single distance segment
                step = Step(
                    kind="warmup" if is_warmup else "cooldown" if is_cooldown else "steady",
                    distance_m=distance_m,
                    target=target
                )
                steps.append(step)
        elif distance_range:
            # Parse distance range (e.g., "25-30m")
            match = re.search(r'(\d+)-(\d+)', distance_range)
            if match:
                min_dist = int(match.group(1))
                max_dist = int(match.group(2))
                avg_dist = (min_dist + max_dist) // 2
                step = Step(
                    kind="warmup" if is_warmup else "cooldown" if is_cooldown else "steady",
                    distance_m=avg_dist,
                    target=Target()
                )
                steps.append(step)
        elif duration_sec:
            # Time-based steady state
            step = Step(
                kind="warmup" if is_warmup else "cooldown" if is_cooldown else "steady",
                duration_s=duration_sec,
                target=target
            )
            steps.append(step)
            if rest_sec:
                rest_step = Step(
                    kind="rest",
                    duration_s=rest_sec,
                    target=Target()
                )
                steps.append(rest_step)

    # Handle supersets (less common for running/cycling, but handle anyway)
    for superset in block.get("supersets", []):
        for ex in superset.get("exercises", []):
            ex_name = ex.get("name", "").lower()
            distance_m = ex.get("distance_m")
            duration_sec = ex.get("duration_sec")
            rest_sec = ex.get("rest_sec")

            # Check if this is a running/cycling exercise
            is_cardio = any(keyword in ex_name for keyword in [
                "run", "jog", "sprint", "pace", "tempo", "easy", "recovery",
                "bike", "ride", "cycle", "spin", "watt", "ftp", "threshold"
            ])

            if distance_m:
                step = Step(
                    kind="steady",
                    distance_m=distance_m,
                    target=Target()
                )
                steps.append(step)
            elif duration_sec:
                step = Step(
                    kind="steady",
                    duration_s=duration_sec,
                    target=Target()
                )
                steps.append(step)

            if rest_sec:
                rest_step = Step(
                    kind="rest",
                    duration_s=rest_sec,
                    target=Target()
                )
                steps.append(rest_step)

    return steps


def to_zwo(blocks_json: dict, sport: Optional[str] = None) -> str:
    """Convert blocks JSON to Zwift ZWO XML format.
    
    Args:
        blocks_json: The blocks JSON structure
        sport: Either "run" or "ride". If None, will attempt to auto-detect.
    
    Returns:
        ZWO XML string
    """
    title = blocks_json.get("title", "Imported Workout")
    
    # Auto-detect sport if not provided
    if not sport:
        sport = "run"  # Default to run
        # Check blocks for hints about sport type
        for block in blocks_json.get("blocks", []):
            for ex in block.get("exercises", []):
                ex_name = ex.get("name", "").lower()
                if any(keyword in ex_name for keyword in ["bike", "ride", "cycle", "spin", "watt", "ftp"]):
                    sport = "ride"
                    break
            if sport == "ride":
                break
    
    # Convert blocks to steps
    all_steps: List[Step] = []
    for block in blocks_json.get("blocks", []):
        block_steps = block_to_steps(block, sport)
        all_steps.extend(block_steps)
    
    # Create workout structure
    workout = Workout(
        sport=sport,
        name=title,
        steps=all_steps
    )
    
    # Generate ZWO XML
    return export_zwo(workout)


def export_zwo(workout: Workout) -> str:
    """Produce a Zwift .zwo string.
    
    Assumptions:
      - Intensity values are 0.00–1.00 scalars where 1.00 = threshold (FTP/CP for bike; threshold pace/speed for run).
      - If target.min/max missing, fall back to 0.70 (endurance).
      - Distance-based steps are converted to duration placeholders if no duration is present (60s per 200m heuristic).
    """
    zwo = Element("workout_file")
    _add_text(zwo, "name", workout.name)
    _add_text(zwo, "sportType", "run" if workout.sport == "run" else "bike")
    _add_text(zwo, "description", f"Auto-generated from canonical JSON → ZWO")
    
    w_el = SubElement(zwo, "workout")
    
    for s in workout.steps:
        # Normalize duration
        dur = _duration_seconds(s)
        
        if s.kind in ("steady", "warmup", "cooldown"):
            el = SubElement(w_el, "SteadyState")
            el.set("Duration", str(dur))
            _apply_target(el, s, steady=True, sport=workout.sport)
        
        elif s.kind == "interval" and s.reps and s.work_s and s.rest_s:
            el = SubElement(w_el, "IntervalsT")
            el.set("Repeat", str(s.reps))
            el.set("OnDuration", str(s.work_s))
            el.set("OffDuration", str(s.rest_s))
            _apply_target(el, s, steady=False, sport=workout.sport)
        
        elif s.kind == "rest":
            el = SubElement(w_el, "SteadyState")
            el.set("Duration", str(dur))
            # Rest intensity fallback
            _set_intensity(el, workout.sport, on=False, value=0.40)
        
        else:
            # Fallback: 60s at 0.60
            el = SubElement(w_el, "SteadyState")
            el.set("Duration", str(dur or 60))
            _set_intensity(el, workout.sport, on=True, value=0.60)
    
    # Generate XML with proper formatting
    xml_str = tostring(zwo, encoding="unicode")
    
    # Add XML declaration and basic formatting
    # Note: ElementTree's tostring() doesn't pretty-print by default,
    # but TrainingPeaks should accept the XML as-is
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

