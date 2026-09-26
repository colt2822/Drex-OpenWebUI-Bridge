from __future__ import annotations

from typing import Any


def format_answer(question: dict[str, Any], answer: dict[str, Any]) -> str:
    labels = question["criteria"]
    lines = [f"Selected: {labels[answer['choice']]}"]
    confidence = answer.get("confidence")
    if isinstance(confidence, (float, int)) and not isinstance(confidence, bool):
        lines[0] += f"\nDecision confidence: {confidence:.1%}"
    lines.extend(["", "Probability distribution:"])
    for key, probability in sorted(answer["probabilities"].items(), key=lambda item: item[1], reverse=True):
        value = "<0.1%" if probability < .001 else f"{probability:.1%}"
        lines.append(f"- {labels[key]}: {value}")
    return "\n".join(lines)
