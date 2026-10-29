"""
Feature Parser Module
=====================
Parses feature extraction text files from Gemini models into structured JSON.
Implements consensus voting protocol to reconcile differences between model outputs.

Supports both:
- STEP file feature extractions (features_eixo_step_Gemini*.txt)
- Drawing file feature extractions (draw_features_eixo_Gemini*.txt)

Feature format (from actual files):
    N. FeatureType
       Description: ...
       Absolute Location: X:x, Y:y, Z:z
       Relative Position: X:x, Y:y, Z:z
       Dimensions: Ø:d, L:l, ...
       Orientation: ...
       Tolerance: ... (optional)
"""

import re
import json
import os
from typing import Dict, List, Optional, Tuple


def parse_feature_file(filepath: str) -> List[Dict]:
    """
    Parse a feature extraction text file into structured data.
    
    Args:
        filepath: Path to the feature text file
        
    Returns:
        List of feature dictionaries with keys:
        - id: Feature number
        - type: Feature type (Step, Chamfer, Blind Hole, etc.)
        - description: Text description
        - absolute_location: {X, Y, Z} coordinates
        - relative_position: {X, Y, Z} coordinates
        - dimensions: Dict of dimension key-value pairs
        - orientation: Orientation description
        - tolerance: Tolerance specification (if present)
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    features = []
    # Split by feature pattern "N. FeatureType" — the marker's type name can be
    # multi-word ("Blind Hole", "Through Hole"), so this must capture the whole
    # line, not just its first word (a single \w+ here silently truncated
    # "Blind Hole" -> "Blind" and "Through Hole" -> "Through", which then failed
    # to match ontology.py's FEATURE_TO_OPERATION keys and fell through to its
    # default-turning fallback for those features).
    feature_blocks = re.split(r'\n(\d+\.\s+[^\n]+)', content)
    
    # feature_blocks[0] is the header, then pairs of (marker, block)
    i = 1
    while i < len(feature_blocks) - 1:
        marker = feature_blocks[i].strip()
        block = feature_blocks[i + 1]
        
        # Extract feature number and type from marker
        marker_match = re.match(r'(\d+)\.\s+(\w[\w\s]*)', marker)
        if not marker_match:
            i += 2
            continue
            
        feature_id = int(marker_match.group(1))
        feature_type = marker_match.group(2).strip()
        
        # Parse fields from block
        feature = {
            'id': feature_id,
            'type': feature_type,
            'description': '',
            'absolute_location': {},
            'relative_position': {},
            'dimensions': {},
            'orientation': '',
            'tolerance': 'General'  # Default
        }
        
        # Parse Description
        desc_match = re.search(r'Description:\s*(.+)', block)
        if desc_match:
            feature['description'] = desc_match.group(1).strip()
        
        # Parse Absolute Location
        abs_match = re.search(r'Absolute Location:\s*X:([^,\n]+),\s*Y:([^,\n]+),\s*Z:([^,\n]+)', block)
        if abs_match:
            feature['absolute_location'] = {
                'X': float(abs_match.group(1).strip()),
                'Y': float(abs_match.group(2).strip()),
                'Z': float(abs_match.group(3).strip())
            }
        
        # Parse Relative Position
        rel_match = re.search(r'Relative Position:\s*X:([^,\n]+),\s*Y:([^,\n]+),\s*Z:([^,\n]+)', block)
        if rel_match:
            feature['relative_position'] = {
                'X': float(rel_match.group(1).strip()),
                'Y': float(rel_match.group(2).strip()),
                'Z': float(rel_match.group(3).strip())
            }
        
        # Parse Dimensions (handle Ø, R, L, W, etc.)
        dim_match = re.search(r'Dimensions:\s*(.+)', block)
        if dim_match:
            dim_str = dim_match.group(1).strip()
            # Parse key:value pairs
            dim_pairs = re.findall(r'(Ø|R|L|W):([^,\s]+)', dim_str)
            for key, value in dim_pairs:
                try:
                    feature['dimensions'][key] = float(value)
                except ValueError:
                    feature['dimensions'][key] = value
        
        # Parse Orientation
        orient_match = re.search(r'Orientation:\s*(.+)', block)
        if orient_match:
            feature['orientation'] = orient_match.group(1).strip()
        
        # Parse Tolerance (optional)
        tol_match = re.search(r'Tolerance:\s*(.+)', block)
        if tol_match:
            feature['tolerance'] = tol_match.group(1).strip()
        
        features.append(feature)
        i += 2
    
    return features


def parse_overall_dimensions(content: str) -> Dict:
    """
    Parse overall dimensions and center point from feature file header.
    
    Returns:
        Dict with overall_dimensions and center_point
    """
    result = {
        'overall_dimensions': {},
        'center_point': {}
    }
    
    # Parse Overall Dimensions
    dim_match = re.search(r'Overall Dimensions:\s*L:([^,\n]+),\s*W:([^,\n]+),\s*H:([^,\n]+)', content)
    if dim_match:
        result['overall_dimensions'] = {
            'L': float(dim_match.group(1).strip()),
            'W': float(dim_match.group(2).strip()),
            'H': float(dim_match.group(3).strip())
        }
    
    # Parse Center Point
    center_match = re.search(r'Center Point:\s*X:([^,\n]+),\s*Y:([^,\n]+),\s*Z:([^,\n]+)', content)
    if center_match:
        result['center_point'] = {
            'X': float(center_match.group(1).strip()),
            'Y': float(center_match.group(2).strip()),
            'Z': float(center_match.group(3).strip())
        }
    
    return result


def load_features_from_file(filepath: str) -> Dict:
    """
    Load complete feature data from a file including metadata.
    
    Returns:
        Dict with features list and overall metadata
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    features = parse_feature_file(filepath)
    metadata = parse_overall_dimensions(content)
    
    # Add source information
    source_name = os.path.basename(filepath)
    
    return {
        'source': source_name,
        'filepath': filepath,
        'metadata': metadata,
        'features': features,
        'feature_count': len(features)
    }


# Type-admissibility gate (manuscript Eq. 3, tau_min). A candidate pair is only
# scored when its categorical type similarity reaches this tier: 1.0 (identical
# label) or 0.7 (declared same-family renaming). Cross-family lookalikes (0.3)
# and unrelated types (0.0) are never merged, however close their locations or
# dimensions are. Set to 0.0 to reproduce the ablation (additive score alone).
TYPE_GATE = 0.7


def reconcile_features(
    features_primary: List[Dict],
    features_secondary: List[Dict],
    primary_weight: float = 0.6,
    secondary_weight: float = 0.4,
    type_gate: Optional[float] = None,
    match_threshold: float = 0.5,
) -> List[Dict]:
    """
    Apply consensus voting protocol to reconcile two model outputs.
    
    Implements Eq. 2 from manuscript: confidence-weighted multi-agent consensus.
    Features are matched by type and spatial proximity, then merged with weights.
    
    Args:
        features_primary: Features from primary model (e.g., Gemini 3.1 Pro)
        features_secondary: Features from secondary model (e.g., Gemini 3.5 Flash)
        primary_weight: Confidence weight for primary model (default 0.6)
        secondary_weight: Confidence weight for secondary model (default 0.4)
        
    Returns:
        List of reconciled feature dictionaries with confidence scores
    """
    if type_gate is None:
        type_gate = TYPE_GATE  # read at call time so an ablation can override the module value
    reconciled = []
    matched_secondary = set()
    
    for primary_feat in features_primary:
        best_match = None
        best_score = 0.0
        
        # Find best matching feature from secondary model
        for idx, secondary_feat in enumerate(features_secondary):
            if idx in matched_secondary:
                continue

            # Categorical gate (Eq. 3, first conjunct): type agreement is a
            # necessary condition, evaluated before the metric score so that
            # spatial and dimensional agreement can never substitute for it.
            if calculate_type_similarity(primary_feat['type'], secondary_feat['type']) < type_gate:
                continue

            # Calculate match score based on type and location similarity
            score = calculate_match_score(primary_feat, secondary_feat)
            
            if score > best_score:
                best_score = score
                best_match = (idx, secondary_feat)
        
        if best_match and best_score > match_threshold:  # Eq. 3, second conjunct (theta)
            idx, secondary_feat = best_match
            matched_secondary.add(idx)
            
            # Merge features with confidence weights
            merged = merge_features(primary_feat, secondary_feat, primary_weight, secondary_weight)
            merged['match_confidence'] = best_score
            merged['reconciliation'] = 'merged'
            reconciled.append(merged)
        else:
            # No match found, use primary feature only
            primary_feat['match_confidence'] = 1.0
            primary_feat['reconciliation'] = 'primary_only'
            reconciled.append(primary_feat)
    
    # Add unmatched secondary features
    for idx, secondary_feat in enumerate(features_secondary):
        if idx not in matched_secondary:
            secondary_feat['match_confidence'] = secondary_weight
            secondary_feat['reconciliation'] = 'secondary_only'
            reconciled.append(secondary_feat)
    
    return reconciled


def euclidean_distance(point1: Tuple[float, ...], point2: Tuple[float, ...]) -> float:
    """
    Calculate Euclidean distance between two points.
    
    Args:
        point1: First point as tuple of coordinates
        point2: Second point as tuple of coordinates
        
    Returns:
        Euclidean distance between the two points
    """
    import math
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(point1, point2)))


def calculate_match_score(feat1: Dict, feat2: Dict) -> float:
    """
    Calculate similarity score between two features.
    
    Considers:
    - Type match (exact or semantic similarity)
    - Location proximity (Euclidean distance in 3D)
    - Dimension similarity
    """
    score = 0.0
    
    # Type similarity (0-0.4)
    type_score = calculate_type_similarity(feat1['type'], feat2['type'])
    score += 0.4 * type_score
    
    # Location similarity (0-0.4)
    loc1 = feat1.get('absolute_location', {})
    loc2 = feat2.get('absolute_location', {})
    
    if loc1 and loc2:
        dist = euclidean_distance(
            (loc1.get('X', 0), loc1.get('Y', 0), loc1.get('Z', 0)),
            (loc2.get('X', 0), loc2.get('Y', 0), loc2.get('Z', 0))
        )
        # Convert distance to similarity (max distance ~50mm = 0 similarity)
        loc_sim = max(0, 1.0 - dist / 50.0)
        score += 0.4 * loc_sim
    
    # Dimension similarity (0-0.2)
    dim_sim = calculate_dimension_similarity(feat1.get('dimensions', {}), feat2.get('dimensions', {}))
    score += 0.2 * dim_sim
    
    return score


def calculate_type_similarity(type1: str, type2: str) -> float:
    """
    Calculate semantic similarity between feature types.

    Handles cases where models use different names for similar features:
    - "Step" vs "Cylinder" (both cylindrical bodies)
    - "Through Hole" vs "Slot" (both can be cylindrical cutouts, but this is a
      much weaker signal than the hole-family renamings below — a slot is a
      milling feature, not a hole, so it gets its own lower-scored tier
      instead of full partial-match credit; see partial_equivalences).
    """
    if type1.lower() == type2.lower():
        return 1.0

    # Same-feature-family renamings across models: strong partial match.
    equivalences = {
        'through hole': ['hole'],
        'step': ['cylinder', 'boss'],
        'cylinder': ['step', 'boss'],
        'boss': ['step', 'cylinder'],
        'blind hole': ['hole', 'bore'],
        'hole': ['blind hole', 'bore', 'through hole'],
        'bore': ['blind hole', 'hole'],
        'chamfer': ['groove'],
        'groove': ['chamfer'],
    }

    # Weaker, cross-family lookalikes: contribute some signal but, at this
    # score, can't push a merge over reconcile_features' 0.5 threshold on
    # type alone — real location/dimension corroboration is still required.
    partial_equivalences = {
        'hole': ['slot'],
        'through hole': ['slot'],
        'slot': ['hole', 'through hole'],
    }

    type1_lower = type1.lower()
    type2_lower = type2.lower()

    if type2_lower in equivalences.get(type1_lower, []):
        return 0.7  # Partial match
    if type2_lower in partial_equivalences.get(type1_lower, []):
        return 0.3  # Weak/cross-family match

    return 0.0


def calculate_dimension_similarity(dim1: Dict, dim2: Dict) -> float:
    """
    Calculate similarity between dimension dictionaries.
    Compares common dimension keys (Ø, R, L, W).
    """
    if not dim1 or not dim2:
        return 0.0
    
    common_keys = set(dim1.keys()) & set(dim2.keys())
    if not common_keys:
        return 0.0
    
    similarities = []
    for key in common_keys:
        val1 = dim1[key]
        val2 = dim2[key]
        
        if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
            if val1 == 0 and val2 == 0:
                sim = 1.0
            else:
                max_val = max(abs(val1), abs(val2))
                sim = max(0, 1.0 - abs(val1 - val2) / max_val) if max_val > 0 else 0.0
            similarities.append(sim)
    
    return sum(similarities) / len(similarities) if similarities else 0.0


def merge_features(
    feat1: Dict,
    feat2: Dict,
    weight1: float,
    weight2: float
) -> Dict:
    """
    Merge two features with confidence weights.
    Prioritizes more specific/detailed values.
    """
    merged = {
        'id': feat1['id'],
        'type': feat1['type'],  # Primary type as canonical
        'description': feat1['description'],
        'absolute_location': {},
        'relative_position': {},
        'dimensions': {},
        'orientation': feat1['orientation'],
        'tolerance': feat2.get('tolerance', 'General'),  # Secondary often has tolerance data
        'source_primary': feat1,
        'source_secondary': feat2,
    }
    
    # Merge locations (weighted average if both present)
    loc1 = feat1.get('absolute_location', {})
    loc2 = feat2.get('absolute_location', {})
    
    for key in ['X', 'Y', 'Z']:
        if key in loc1 and key in loc2:
            merged['absolute_location'][key] = weight1 * loc1[key] + weight2 * loc2[key]
        elif key in loc1:
            merged['absolute_location'][key] = loc1[key]
        elif key in loc2:
            merged['absolute_location'][key] = loc2[key]
    
    # Merge dimensions (take union, prefer non-zero values)
    dim1 = feat1.get('dimensions', {})
    dim2 = feat2.get('dimensions', {})
    
    all_keys = set(dim1.keys()) | set(dim2.keys())
    for key in all_keys:
        if key in dim1 and key in dim2:
            # Both have it, use weighted average for numeric
            if isinstance(dim1[key], (int, float)) and isinstance(dim2[key], (int, float)):
                merged['dimensions'][key] = weight1 * dim1[key] + weight2 * dim2[key]
            else:
                merged['dimensions'][key] = dim1[key]  # Prefer primary
        elif key in dim1:
            merged['dimensions'][key] = dim1[key]
        else:
            merged['dimensions'][key] = dim2[key]
    
    return merged


def features_to_json(features: List[Dict], filepath: Optional[str] = None) -> str:
    """
    Convert features list to JSON string.
    Optionally save to file.
    
    Returns:
        JSON string representation
    """
    json_str = json.dumps(features, indent=2, ensure_ascii=False)
    
    if filepath:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(json_str)
    
    return json_str


if __name__ == '__main__':
    # Test with actual feature files
    import sys
    
    # Paths to feature files
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    motor_data_dir = os.path.join(base_dir, 'data', 'motor_data')
    
    # Try to load and parse feature files
    feature_files = [
        'features_eixo_step_Gemini31Pro.txt',
        'features_eixo_step_Gemini35flash.txt'
    ]
    
    print("=" * 60)
    print("Feature Parser Test")
    print("=" * 60)
    
    all_features = {}
    for filename in feature_files:
        filepath = os.path.join(motor_data_dir, filename)
        if os.path.exists(filepath):
            print(f"\nLoading: {filename}")
            data = load_features_from_file(filepath)
            all_features[filename] = data
            print(f"  Features found: {data['feature_count']}")
            print(f"  Overall dimensions: {data['metadata']['overall_dimensions']}")
            
            # Print feature types
            for feat in data['features']:
                print(f"  - {feat['id']}. {feat['type']}: {feat['description'][:50]}...")
        else:
            print(f"\nFile not found: {filepath}")
    
    # Test reconciliation
    if len(all_features) == 2:
        print("\n" + "=" * 60)
        print("Feature Reconciliation")
        print("=" * 60)
        
        primary = list(all_features.values())[0]['features']
        secondary = list(all_features.values())[1]['features']
        
        reconciled = reconcile_features(primary, secondary)
        
        print(f"\nPrimary features: {len(primary)}")
        print(f"Secondary features: {len(secondary)}")
        print(f"Reconciled features: {len(reconciled)}")
        
        for feat in reconciled:
            status = feat.get('reconciliation', 'unknown')
            confidence = feat.get('match_confidence', 0)
            print(f"  - {feat['id']}. {feat['type']}: {status} (confidence: {confidence:.2f})")
        
        # Save reconciled features
        output_path = os.path.join(base_dir, 'data', 'reconciled_features.json')
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        features_to_json(reconciled, output_path)
        print(f"\nReconciled features saved to: {output_path}")
