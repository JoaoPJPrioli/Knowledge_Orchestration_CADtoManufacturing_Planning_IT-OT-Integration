"""
LLM Benchmark Configuration Module
===================================
Configuration for LLM benchmark testing including model settings,
test datasets, and evaluation parameters.

Models Tested (per manuscript):
- Gemini 2.0 Flash
- Gemini 2.5 Pro
- Gemini 2.5 Flash

Configuration Includes:
- Model parameters (temperature, max tokens, etc.)
- Test query datasets (ModelNet-10, ShapeNet-10 inspired)
- Evaluation metrics settings
- Cost tracking parameters

Usage:
    from benchmark_config import MODEL_CONFIGS, TEST_QUERIES
    for model_config in MODEL_CONFIGS:
        print(f"Testing {model_config['name']}...")
"""

from typing import Dict, List, Any

# === Model Configurations ===
MODEL_CONFIGS: List[Dict[str, Any]] = [
    {
        "name": "Gemini 2.0 Flash",
        "model_id": "gemini-2.0-flash",
        "temperature": 0.1,
        "max_output_tokens": 2048,
        "top_p": 0.8,
        "top_k": 40,
        "timeout": 30,  # seconds
        "cost_per_1m_input": 0.00,  # Placeholder - update with actual pricing
        "cost_per_1m_output": 0.00,
        "description": "Fast, efficient model for SPARQL generation"
    },
    {
        "name": "Gemini 2.5 Pro",
        "model_id": "gemini-2.5-pro",
        "temperature": 0.1,
        "max_output_tokens": 2048,
        "top_p": 0.9,
        "top_k": 40,
        "timeout": 60,
        "cost_per_1m_input": 0.00,
        "cost_per_1m_output": 0.00,
        "description": "High-quality model for complex SPARQL queries"
    },
    {
        "name": "Gemini 2.5 Flash",
        "model_id": "gemini-2.5-flash",
        "temperature": 0.1,
        "max_output_tokens": 2048,
        "top_p": 0.85,
        "top_k": 40,
        "timeout": 45,
        "cost_per_1m_input": 0.00,
        "cost_per_1m_output": 0.00,
        "description": "Balanced model for SPARQL generation"
    }
]

# === Test Query Datasets ===
# Inspired by ModelNet-10 and ShapeNet-10 categories
# Categories: Airplane, Bag, Cap, Car, Chair, Earphone, Guitar, Knife, Lamp, Laptop

TEST_QUERIES: List[Dict[str, Any]] = [
    # Feature queries (ModelNet-10: Chair, Lamp, Guitar categories)
    {
        "id": 1,
        "question": "What operations are required for feature 1001?",
        "category": "feature",
        "difficulty": "easy",
        "expected_pattern": "SELECT ?operation WHERE { ?feature mfg:requires ?operation }",
        "ground_truth_operations": ["turning", "facing"]
    },
    {
        "id": 2,
        "question": "List all features in the knowledge graph.",
        "category": "feature",
        "difficulty": "easy",
        "expected_pattern": "SELECT ?feature WHERE { ?feature rdf:type mfg:Feature }",
        "ground_truth_count": 5
    },
    {
        "id": 3,
        "question": "What are the dimensions of feature 1002?",
        "category": "feature",
        "difficulty": "medium",
        "expected_pattern": "SELECT ?dimKey ?dimValue WHERE { ?feature mfg:hasDimension ?dimension }",
        "ground_truth_dimensions": ["diameter", "length"]
    },
    {
        "id": 4,
        "question": "Find features with diameter greater than 50mm.",
        "category": "feature",
        "difficulty": "medium",
        "expected_pattern": "FILTER (xsd:double(?diameter) > 50.0)",
        "ground_truth_count": 2
    },
    {
        "id": 5,
        "question": "What is the location of feature 1001?",
        "category": "feature",
        "difficulty": "easy",
        "expected_pattern": "SELECT ?coordinates WHERE { ?feature mfg:locatedAt ?location }",
        "ground_truth_location": {"x": 0, "y": 0, "z": 25}
    },
    
    # Operation queries (ModelNet-10: Car, Knife categories)
    {
        "id": 6,
        "question": "What tools are used for the facing operation?",
        "category": "operation",
        "difficulty": "easy",
        "expected_pattern": "SELECT ?tool WHERE { ?operation mfg:uses ?tool }",
        "ground_truth_tools": ["facing_tool"]
    },
    {
        "id": 7,
        "question": "List all operations in the machining sequence.",
        "category": "operation",
        "difficulty": "medium",
        "expected_pattern": "SELECT ?operation WHERE { ?operation rdf:type mfg:Operation }",
        "ground_truth_count": 5
    },
    {
        "id": 8,
        "question": "What machine is used for turning operations?",
        "category": "operation",
        "difficulty": "easy",
        "expected_pattern": "SELECT ?machine WHERE { ?operation mfg:runsOn ?machine }",
        "ground_truth_machine": "cnc_lathe"
    },
    {
        "id": 9,
        "question": "Which operations remove steel_1045 material?",
        "category": "operation",
        "difficulty": "medium",
        "expected_pattern": "SELECT ?operation WHERE { ?operation mfg:removes ?material }",
        "ground_truth_operations": ["turning", "facing", "grooving"]
    },
    {
        "id": 10,
        "question": "Find operations that use carbide tools.",
        "category": "operation",
        "difficulty": "hard",
        "expected_pattern": "FILTER (?tool mfg:materialType \"carbide\")",
        "ground_truth_count": 3
    },
    
    # Tool queries (ModelNet-10: Earphone, Laptop categories)
    {
        "id": 11,
        "question": "What is the geometry of the turning tool?",
        "category": "tool",
        "difficulty": "easy",
        "expected_pattern": "SELECT ?geometry WHERE { ?tool mfg:geometry ?geometry }",
        "ground_truth_geometry": "35_degree_insert"
    },
    {
        "id": 12,
        "question": "List all tools and their materials.",
        "category": "tool",
        "difficulty": "easy",
        "expected_pattern": "SELECT ?toolName ?materialType WHERE { ?tool mfg:materialType ?materialType }",
        "ground_truth_count": 5
    },
    {
        "id": 13,
        "question": "Which operations use the drill bit tool?",
        "category": "tool",
        "difficulty": "medium",
        "expected_pattern": "SELECT ?operation WHERE { ?operation mfg:uses ?tool }",
        "ground_truth_operations": ["drilling"]
    },
    {
        "id": 14,
        "question": "What tools are recommended for grooving operations?",
        "category": "tool",
        "difficulty": "easy",
        "expected_pattern": "SELECT ?tool WHERE { ?operation mfg:uses ?tool }",
        "ground_truth_tools": ["groove_tool"]
    },
    {
        "id": 15,
        "question": "Find tools made of high-speed steel.",
        "category": "tool",
        "difficulty": "medium",
        "expected_pattern": "FILTER (?tool mfg:materialType \"high-speed steel\")",
        "ground_truth_count": 2
    },
    
    # Sequence queries (ModelNet-10: Airplane, Bag categories)
    {
        "id": 16,
        "question": "What is the complete machining sequence?",
        "category": "sequence",
        "difficulty": "medium",
        "expected_pattern": "SELECT ?op1 ?op2 WHERE { ?op1 mfg:sequenceBefore ?op2 }",
        "ground_truth_sequence": ["facing", "turning", "grooving", "threading"]
    },
    {
        "id": 17,
        "question": "Which operation comes first in the sequence?",
        "category": "sequence",
        "difficulty": "hard",
        "expected_pattern": "FILTER NOT EXISTS { ?otherOp mfg:sequenceBefore ?firstOp }",
        "ground_truth_operation": "facing"
    },
    {
        "id": 18,
        "question": "What operation comes after facing?",
        "category": "sequence",
        "difficulty": "medium",
        "expected_pattern": "?facingOp mfg:sequenceBefore ?nextOp",
        "ground_truth_operation": "turning"
    },
    {
        "id": 19,
        "question": "How many operations are in the machining sequence?",
        "category": "sequence",
        "difficulty": "easy",
        "expected_pattern": "SELECT (COUNT(?operation) AS ?count)",
        "ground_truth_count": 5
    },
    {
        "id": 20,
        "question": "What is the last operation in the sequence?",
        "category": "sequence",
        "difficulty": "hard",
        "expected_pattern": "FILTER NOT EXISTS { ?lastOp mfg:sequenceBefore ?otherOp }",
        "ground_truth_operation": "threading"
    },
    
    # Complex multi-hop queries (ModelNet-10: Cap, Chair categories)
    {
        "id": 21,
        "question": "What tools are needed for feature 1001?",
        "category": "complex",
        "difficulty": "hard",
        "expected_pattern": "?feature mfg:requires ?operation . ?operation mfg:uses ?tool",
        "ground_truth_tools": ["turning_tool", "facing_tool"]
    },
    {
        "id": 22,
        "question": "What machine and tools are used for feature 1002?",
        "category": "complex",
        "difficulty": "hard",
        "expected_pattern": "?operation mfg:runsOn ?machine . ?operation mfg:uses ?tool",
        "ground_truth_machine": "cnc_lathe",
        "ground_truth_tools": ["groove_tool"]
    },
    {
        "id": 23,
        "question": "What is the complete manufacturing plan for feature 1001?",
        "category": "complex",
        "difficulty": "hard",
        "expected_pattern": "SELECT ?operation ?tool ?machine",
        "ground_truth_steps": 3
    },
    {
        "id": 24,
        "question": "Find all features that use the same tool as feature 1001.",
        "category": "complex",
        "difficulty": "hard",
        "expected_pattern": "FILTER (?otherFeature != ?feature1)",
        "ground_truth_count": 2
    },
    {
        "id": 25,
        "question": "What materials are removed by operations on cylinder features?",
        "category": "complex",
        "difficulty": "hard",
        "expected_pattern": "FILTER (CONTAINS(?featureName, \"cylinder\"))",
        "ground_truth_materials": ["steel_1045"]
    },
    
    # Additional queries for robustness testing
    {
        "id": 26,
        "question": "List all operations with their tools and machines.",
        "category": "complex",
        "difficulty": "medium",
        "expected_pattern": "SELECT ?opName ?toolName ?machineName",
        "ground_truth_count": 5
    },
    {
        "id": 27,
        "question": "What is the total number of triples in the knowledge graph?",
        "category": "complex",
        "difficulty": "easy",
        "expected_pattern": "SELECT (COUNT(?s) AS ?count) WHERE { ?s ?p ?o }",
        "ground_truth_min_count": 50
    },
    {
        "id": 28,
        "question": "Find features that require multiple operations.",
        "category": "complex",
        "difficulty": "hard",
        "expected_pattern": "GROUP BY ?feature HAVING (COUNT(?operation) > 1)",
        "ground_truth_count": 3
    },
    {
        "id": 29,
        "question": "What operations are performed on steel material?",
        "category": "operation",
        "difficulty": "medium",
        "expected_pattern": "FILTER (CONTAINS(?materialName, \"steel\"))",
        "ground_truth_operations": ["turning", "facing", "grooving"]
    },
    {
        "id": 30,
        "question": "Generate a complete manufacturing report.",
        "category": "complex",
        "difficulty": "hard",
        "expected_pattern": "SELECT ?featureName ?opName ?toolName ?machineName",
        "ground_truth_sections": ["features", "operations", "tools", "machines"]
    }
]

# === Evaluation Settings ===
EVALUATION_SETTINGS: Dict[str, Any] = {
    "metrics": [
        "accuracy",
        "precision",
        "recall",
        "f1_score",
        "latency_ms",
        "cost_usd",
        "syntax_validity",
        "semantic_correctness"
    ],
    "thresholds": {
        "latency_warning_ms": 5000,  # 5 seconds
        "latency_critical_ms": 15000,  # 15 seconds
        "cost_warning_usd": 0.01,  # 1 cent per query
        "accuracy_target": 0.85,  # 85% accuracy target
        "f1_target": 0.80  # 80% F1 score target
    },
    "retries": {
        "max_retries": 3,
        "retry_delay_seconds": 1,
        "retry_on_timeout": True
    },
    "caching": {
        "enable_cache": False,  # Disable for benchmarking
        "cache_ttl_seconds": 0
    }
}

# === Benchmark Report Settings ===
REPORT_SETTINGS: Dict[str, Any] = {
    "output_format": ["markdown", "json", "csv"],
    "include_charts": True,
    "chart_types": [
        "accuracy_comparison",
        "latency_comparison",
        "cost_comparison",
        "cost_latency_tradeoff",
        "accuracy_by_difficulty",
        "accuracy_by_category"
    ],
    "summary_sections": [
        "executive_summary",
        "model_comparison",
        "cost_analysis",
        "latency_analysis",
        "accuracy_analysis",
        "recommendations"
    ],
    "visualization": {
        "dpi": 300,
        "figure_size": (12, 8),
        "color_palette": ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    }
}

def get_model_config(model_name: str) -> Dict[str, Any]:
    """
    Get configuration for a specific model.
    
    Args:
        model_name: Model name (e.g., "Gemini 2.0 Flash")
        
    Returns:
        Model configuration dictionary
    """
    for config in MODEL_CONFIGS:
        if config["name"] == model_name or config["model_id"] == model_name:
            return config
    
    raise ValueError(f"Unknown model: {model_name}. Available models: {[m['name'] for m in MODEL_CONFIGS]}")

def get_queries_by_category(category: str) -> List[Dict[str, Any]]:
    """
    Get test queries filtered by category.
    
    Args:
        category: Query category (feature, operation, tool, sequence, complex)
        
    Returns:
        List of query dictionaries
    """
    return [q for q in TEST_QUERIES if q["category"] == category]

def get_queries_by_difficulty(difficulty: str) -> List[Dict[str, Any]]:
    """
    Get test queries filtered by difficulty.
    
    Args:
        difficulty: Query difficulty (easy, medium, hard)
        
    Returns:
        List of query dictionaries
    """
    return [q for q in TEST_QUERIES if q["difficulty"] == difficulty]

def get_benchmark_summary() -> Dict[str, Any]:
    """
    Get summary of benchmark configuration.
    
    Returns:
        Dict with benchmark summary
    """
    return {
        "models": len(MODEL_CONFIGS),
        "total_queries": len(TEST_QUERIES),
        "categories": len(set(q["category"] for q in TEST_QUERIES)),
        "difficulties": len(set(q["difficulty"] for q in TEST_QUERIES)),
        "metrics": EVALUATION_SETTINGS["metrics"],
        "report_formats": REPORT_SETTINGS["output_format"]
    }
