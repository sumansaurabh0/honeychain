def assess(reading):
    # Rule-based score; not a definitive disease diagnosis.
    score, reasons = 100, []
    for value, low, high, label in ((reading.temperature, 20, 35, "Temperature"), (reading.humidity, 40, 75, "Humidity")):
        if not low <= value <= high:
            score -= 20
            reasons.append(f"{label} outside expected range")
    for value, limit, label in ((reading.gas_raw, 2500, "Gas level"), (reading.mic_raw, 3000, "Sound level")):
        if value > limit:
            score -= 20
            reasons.append(f"{label} elevated")
    if reading.weight <= 0:
        score -= 30
        reasons.append("Weight reading is invalid")
    score = max(score, 0)
    risk = "low" if score >= 80 else "medium" if score >= 60 else "high"
    return {"health_score": score, "risk_level": risk, "reasons": reasons,
            "recommendation": "Continue routine monitoring." if not reasons else "Potential abnormal condition — inspect hive."}
