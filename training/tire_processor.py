import re
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class TireSpec:
    width: int
    aspect_ratio: int
    diameter: int
    codes: List[str]
    original: str

class TireProcessor:
    @staticmethod
    def parse_tire_string(tire_str: str) -> Optional[TireSpec]:
        """Parst einen Reifenstring in seine Komponenten"""
        try:
            # Extrahiere Reifengröße
            size_match = re.search(r'(\d{3})/(\d{2})R(\d{2})', tire_str)
            if not size_match:
                return None
                
            width, ratio, diameter = map(int, size_match.groups())
            
            # Extrahiere Auflagen-Codes
            codes = re.findall(r'([A-Z][0-9]{1,2}[a-z]?|[0-9]{3})', tire_str)
            
            return TireSpec(
                width=width,
                aspect_ratio=ratio,
                diameter=diameter,
                codes=codes,
                original=tire_str.strip()
            )
        except Exception:
            return None

    @staticmethod
    def validate_tire_wheel_combo(tire: TireSpec, wheel_width: float, wheel_diameter: int) -> Dict:
        """Validiert Reifen-Felgen Kombination"""
        result = {
            'valid': False,
            'warnings': [],
            'errors': []
        }
        
        # Prüfe Durchmesser
        if tire.diameter != wheel_diameter:
            result['errors'].append(f"Felgendurchmesser ({wheel_diameter}\") passt nicht zur Reifengröße ({tire.diameter}\")")
            return result
            
        # Prüfe Felgenbreite (in mm)
        wheel_width_mm = wheel_width * 25.4
        min_width = wheel_width_mm * 0.95  # 5% Toleranz
        max_width = wheel_width_mm * 1.05
        
        if not (min_width <= tire.width <= max_width):
            result['warnings'].append(
                f"Reifenbreite ({tire.width}mm) könnte problematisch sein "
                f"für Felgenbreite ({wheel_width_mm:.1f}mm)"
            )
            
        result['valid'] = len(result['errors']) == 0
        return result
