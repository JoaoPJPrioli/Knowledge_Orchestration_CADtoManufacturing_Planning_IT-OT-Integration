"""
SPARQL Examples Module
=====================
54 natural-language to SPARQL query pairs: 50 for few-shot learning and
testing of the SPARQL generator, plus 4 parameter-provenance queries.

Categories:
1. Feature queries (1-10)
2. Operation queries (11-20)
3. Tool queries (21-30)
4. Sequence queries (31-40)
5. Complex multi-hop queries (41-50)
6. Parameter-provenance queries (51-54)

Usage:
    from sparql_examples import EXAMPLES
    generator.load_examples(EXAMPLES)
"""

from typing import List, Dict, Any

EXAMPLES: List[Dict[str, Any]] = [
    # === Feature Queries (1-10) ===
    {
        "question": "What operations are required for feature 1?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?operation ?opName
WHERE {
    ?feature mfg:id "1" .
    ?feature mfg:requires ?operation .
    ?operation mfg:name ?opName .
}""",
        "expected_nonempty": True
    },
    {
        "question": "List all features in the knowledge graph.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?feature ?featureName ?featureType
WHERE {
    ?feature rdf:type mfg:Feature .
    ?feature mfg:name ?featureName .
    OPTIONAL { ?feature mfg:featureType ?featureType } .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What are the dimensions of feature 2?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?dimKey ?dimValue
WHERE {
    ?feature mfg:id "2" .
    ?feature mfg:hasDimension ?dimension .
    ?dimension mfg:dimensionKey ?dimKey .
    ?dimension mfg:value ?dimValue .
}""",
        "expected_nonempty": True
    },
    {
        "question": "Find features located at specific coordinates.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?feature ?featureName ?coordinates
WHERE {
    ?feature rdf:type mfg:Feature .
    ?feature mfg:name ?featureName .
    ?feature mfg:locatedAt ?location .
    ?location mfg:coordinates ?coordinates .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What type of feature is feature 3?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?featureName ?featureType
WHERE {
    ?feature mfg:id "3" .
    ?feature mfg:name ?featureName .
    ?feature mfg:featureType ?featureType .
}""",
        "expected_nonempty": True
    },
    {
        "question": "How many features require the turning operation?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT (COUNT(?feature) AS ?featureCount)
WHERE {
    ?feature mfg:requires ?operation .
    ?operation mfg:name ?opName .
    FILTER (CONTAINS(LCASE(?opName), "turning")) .
}""",
        "expected_nonempty": True
    },
    {
        "question": "Find features with diameter greater than 50mm.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?feature ?featureName ?diameter
WHERE {
    ?feature rdf:type mfg:Feature .
    ?feature mfg:name ?featureName .
    ?feature mfg:hasDimension ?dimension .
    ?dimension mfg:dimensionType "diameter" .
    ?dimension mfg:value ?diameter .
    FILTER (xsd:double(?diameter) > 50.0) .
}""",
        "expected_nonempty": False
    },
    {
        "question": "What is the location of feature 1?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?coordinates
WHERE {
    ?feature mfg:id "1" .
    ?feature mfg:locatedAt ?location .
    ?location mfg:coordinates ?coordinates .
}""",
        "expected_nonempty": True
    },
    {
        "question": "List all features and their dimensions.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?featureName ?dimKey ?dimValue
WHERE {
    ?feature rdf:type mfg:Feature .
    ?feature mfg:name ?featureName .
    ?feature mfg:hasDimension ?dimension .
    ?dimension mfg:dimensionKey ?dimKey .
    ?dimension mfg:value ?dimValue .
}""",
        "expected_nonempty": True
    },
    {
        "question": "Find features that have both diameter and length dimensions.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?feature ?featureName
WHERE {
    ?feature rdf:type mfg:Feature .
    ?feature mfg:name ?featureName .
    ?feature mfg:hasDimension ?dim1 .
    ?feature mfg:hasDimension ?dim2 .
    ?dim1 mfg:dimensionType "diameter" .
    ?dim2 mfg:dimensionType "length" .
}""",
        "expected_nonempty": True
    },

    # === Operation Queries (11-20) ===
    {
        "question": "What tools are used for the facing operation?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?tool ?toolName
WHERE {
    ?operation mfg:name ?opName .
    FILTER (CONTAINS(LCASE(?opName), "facing")) .
    ?operation mfg:uses ?tool .
    ?tool mfg:name ?toolName .
}""",
        "expected_nonempty": True
    },
    {
        "question": "List all operations in the machining sequence.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?operation ?opName ?stepFrom ?stepTo
WHERE {
    ?operation rdf:type mfg:Operation .
    ?operation mfg:name ?opName .
    OPTIONAL {
        ?operation mfg:sequenceBefore ?nextOp .
        ?nextOp mfg:id ?stepTo .
    } .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What machine is used for turning operations?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?machine ?machineName
WHERE {
    ?operation mfg:name ?opName .
    FILTER (CONTAINS(LCASE(?opName), "turning")) .
    ?operation mfg:runsOn ?machine .
    ?machine mfg:name ?machineName .
}""",
        "expected_nonempty": True
    },
    {
        "question": "Which operations remove steel_1045 material?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?operation ?opName
WHERE {
    ?operation rdf:type mfg:Operation .
    ?operation mfg:name ?opName .
    ?operation mfg:removes ?material .
    ?material mfg:id "steel_1045" .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What are the G-codes for the grooving operation?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?operation ?opName ?gCodes
WHERE {
    ?operation rdf:type mfg:Operation .
    ?operation mfg:name ?opName .
    FILTER (CONTAINS(LCASE(?opName), "grooving")) .
    OPTIONAL {
        ?operation mfg:hasGCodes ?params .
        ?params mfg:value ?gCodes .
    } .
}""",
        "expected_nonempty": True
    },
    {
        "question": "Find operations that use carbide tools.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?operation ?opName ?toolName
WHERE {
    ?operation rdf:type mfg:Operation .
    ?operation mfg:name ?opName .
    ?operation mfg:uses ?tool .
    ?tool mfg:name ?toolName .
    ?tool mfg:materialType "Carbide" .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What operations are required for cylinder features?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?operation ?opName
WHERE {
    ?feature rdf:type mfg:Feature .
    ?feature mfg:name ?featureName .
    FILTER (CONTAINS(LCASE(?featureName), "cylinder")) .
    ?feature mfg:requires ?operation .
    ?operation mfg:name ?opName .
}""",
        "expected_nonempty": True
    },
    {
        "question": "List all operations and their required tools.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?opName ?toolName
WHERE {
    ?operation rdf:type mfg:Operation .
    ?operation mfg:name ?opName .
    ?operation mfg:uses ?tool .
    ?tool mfg:name ?toolName .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What is the description of the threading operation?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?description
WHERE {
    ?operation mfg:name ?opName .
    FILTER (CONTAINS(LCASE(?opName), "threading")) .
    ?operation mfg:description ?description .
}""",
        "expected_nonempty": False
    },
    {
        "question": "Find operations that run on CNC lathe.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?operation ?opName
WHERE {
    ?operation rdf:type mfg:Operation .
    ?operation mfg:name ?opName .
    ?operation mfg:runsOn ?machine .
    ?machine mfg:name ?machineName .
    FILTER (CONTAINS(LCASE(?machineName), "cnc lathe")) .
}""",
        "expected_nonempty": True
    },

    # === Tool Queries (21-30) ===
    {
        "question": "What is the geometry of the turning tool?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?toolName ?geometry
WHERE {
    ?tool rdf:type mfg:Tool .
    ?tool mfg:name ?toolName .
    FILTER (CONTAINS(LCASE(?toolName), "turning")) .
    ?tool mfg:geometry ?geometry .
}""",
        "expected_nonempty": True
    },
    {
        "question": "List all tools and their materials.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?toolName ?materialType
WHERE {
    ?tool rdf:type mfg:Tool .
    ?tool mfg:name ?toolName .
    ?tool mfg:materialType ?materialType .
}""",
        "expected_nonempty": True
    },
    {
        "question": "Which operations use the drill bit tool?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?operation ?opName
WHERE {
    ?tool rdf:type mfg:Tool .
    ?tool mfg:name ?toolName .
    FILTER (CONTAINS(LCASE(?toolName), "drill")) .
    ?operation mfg:uses ?tool .
    ?operation mfg:name ?opName .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What tools are recommended for grooving operations?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?tool ?toolName
WHERE {
    ?operation mfg:name ?opName .
    FILTER (CONTAINS(LCASE(?opName), "grooving")) .
    ?operation mfg:uses ?tool .
    ?tool mfg:name ?toolName .
}""",
        "expected_nonempty": True
    },
    {
        "question": "Find tools made of high-speed steel.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?tool ?toolName ?geometry
WHERE {
    ?tool rdf:type mfg:Tool .
    ?tool mfg:name ?toolName .
    ?tool mfg:materialType "High-Speed Steel" .
    OPTIONAL { ?tool mfg:geometry ?geometry } .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What is the type of the groove tool?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?toolName ?toolType
WHERE {
    ?tool rdf:type mfg:Tool .
    ?tool mfg:name ?toolName .
    FILTER (CONTAINS(LCASE(?toolName), "grooving")) .
    ?tool mfg:toolType ?toolType .
}""",
        "expected_nonempty": True
    },
    {
        "question": "List all unique tool types in the knowledge graph.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT ?toolType
WHERE {
    ?tool rdf:type mfg:Tool .
    ?tool mfg:toolType ?toolType .
}""",
        "expected_nonempty": True
    },
    {
        "question": "Which features require tools made of carbide?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?feature ?featureName ?toolName
WHERE {
    ?feature rdf:type mfg:Feature .
    ?feature mfg:name ?featureName .
    ?feature mfg:requires ?operation .
    ?operation mfg:uses ?tool .
    ?tool mfg:name ?toolName .
    ?tool mfg:materialType "Carbide" .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What operations use the same tool?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?toolName ?op1Name ?op2Name
WHERE {
    ?tool rdf:type mfg:Tool .
    ?tool mfg:name ?toolName .
    ?op1 mfg:uses ?tool .
    ?op2 mfg:uses ?tool .
    ?op1 mfg:name ?op1Name .
    ?op2 mfg:name ?op2Name .
    FILTER (?op1 != ?op2) .
}""",
        "expected_nonempty": True
    },
    {
        "question": "Find tools with 35-degree geometry.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?tool ?toolName ?geometry
WHERE {
    ?tool rdf:type mfg:Tool .
    ?tool mfg:name ?toolName .
    ?tool mfg:geometry ?geometry .
    FILTER (CONTAINS(?geometry, "35")) .
}""",
        "expected_nonempty": False
    },

    # === Sequence Queries (31-40) ===
    {
        "question": "What is the complete machining sequence?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?op1Name ?op2Name
WHERE {
    ?op1 rdf:type mfg:Operation .
    ?op1 mfg:sequenceBefore ?op2 .
    ?op1 mfg:name ?op1Name .
    ?op2 mfg:name ?op2Name .
} ORDER BY ?op1Name""",
        "expected_nonempty": True
    },
    {
        "question": "Which operation comes first in the sequence?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?firstOp ?firstOpName
WHERE {
    ?firstOp rdf:type mfg:Operation .
    ?firstOp mfg:name ?firstOpName .
    FILTER EXISTS { ?anyFeature mfg:requires ?firstOp } .
    FILTER NOT EXISTS {
        ?otherOp mfg:sequenceBefore ?firstOp .
    } .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What operation comes after facing?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?nextOp ?nextOpName
WHERE {
    ?facingOp mfg:name ?facingName .
    FILTER (CONTAINS(LCASE(?facingName), "facing")) .
    ?facingOp mfg:sequenceBefore ?nextOp .
    ?nextOp mfg:name ?nextOpName .
}""",
        "expected_nonempty": True
    },
    {
        "question": "How many operations are in the machining sequence?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT (COUNT(?operation) AS ?operationCount)
WHERE {
    ?operation rdf:type mfg:Operation .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What is the last operation in the sequence?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?lastOp ?lastOpName
WHERE {
    ?lastOp rdf:type mfg:Operation .
    ?lastOp mfg:name ?lastOpName .
    FILTER EXISTS { ?anyFeature mfg:requires ?lastOp } .
    FILTER NOT EXISTS {
        ?lastOp mfg:sequenceBefore ?otherOp .
    } .
}""",
        "expected_nonempty": True
    },
    {
        "question": "Find operations that are performed before threading.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?prevOp ?prevOpName
WHERE {
    ?threadingOp mfg:name ?threadingName .
    FILTER (CONTAINS(LCASE(?threadingName), "threading")) .
    ?prevOp mfg:sequenceBefore ?threadingOp .
    ?prevOp mfg:name ?prevOpName .
}""",
        "expected_nonempty": False
    },
    {
        "question": "What is the sequence between turning and facing?",
        # UNION is only valid between two graph patterns inside one WHERE
        # clause, not between two full SELECT statements — the original
        # query used "SELECT ... WHERE {...} UNION SELECT ... WHERE {...}"
        # at the top level, which is a SPARQL parse error.
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?op1Name ?op2Name
WHERE {
    {
        ?op1 mfg:name ?op1Name .
        ?op2 mfg:name ?op2Name .
        FILTER (CONTAINS(LCASE(?op1Name), "turning") && CONTAINS(LCASE(?op2Name), "facing")) .
        ?op1 mfg:sequenceBefore ?op2 .
    }
    UNION
    {
        ?op1 mfg:name ?op1Name .
        ?op2 mfg:name ?op2Name .
        FILTER (CONTAINS(LCASE(?op1Name), "facing") && CONTAINS(LCASE(?op2Name), "turning")) .
        ?op1 mfg:sequenceBefore ?op2 .
    }
}""",
        "expected_nonempty": True
    },
    {
        "question": "List operations in sequence order.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?operation ?opName (COUNT(?predecessor) AS ?position)
WHERE {
    ?operation rdf:type mfg:Operation .
    ?operation mfg:name ?opName .
    FILTER EXISTS { ?anyFeature mfg:requires ?operation } .
    OPTIONAL { ?predecessor mfg:sequenceBefore+ ?operation } .
}
GROUP BY ?operation ?opName
ORDER BY ?position""",
        "expected_nonempty": True
    },
    {
        "question": "Which features affect the machining sequence?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?feature ?featureName ?operation ?opName
WHERE {
    ?feature rdf:type mfg:Feature .
    ?feature mfg:name ?featureName .
    ?feature mfg:requires ?operation .
    ?operation mfg:name ?opName .
    ?operation mfg:sequenceBefore ?nextOp .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What operations have sequence dependencies?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT ?operation ?opName
WHERE {
    ?operation rdf:type mfg:Operation .
    ?operation mfg:name ?opName .
    {
        ?operation mfg:sequenceBefore ?otherOp .
    } UNION {
        ?otherOp mfg:sequenceBefore ?operation .
    }
}""",
        "expected_nonempty": True
    },

    # === Complex Multi-hop Queries (41-50) ===
    {
        "question": "What tools are needed for feature 1?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?tool ?toolName
WHERE {
    ?feature mfg:id "1" .
    ?feature mfg:requires ?operation .
    ?operation mfg:uses ?tool .
    ?tool mfg:name ?toolName .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What machine and tools are used for feature 2?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?machineName ?toolName
WHERE {
    ?feature mfg:id "2" .
    ?feature mfg:requires ?operation .
    ?operation mfg:runsOn ?machine .
    ?operation mfg:uses ?tool .
    ?machine mfg:name ?machineName .
    ?tool mfg:name ?toolName .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What is the complete manufacturing plan for feature 1?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?operation ?opName ?toolName ?machineName
WHERE {
    ?feature mfg:id "1" .
    ?feature mfg:requires ?operation .
    ?operation mfg:name ?opName .
    ?operation mfg:uses ?tool .
    ?tool mfg:name ?toolName .
    ?operation mfg:runsOn ?machine .
    ?machine mfg:name ?machineName .
}""",
        "expected_nonempty": True
    },
    {
        "question": "Find all features that use the same tool as feature 1.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?otherFeature ?otherFeatureName ?toolName
WHERE {
    ?feature1 mfg:id "1" .
    ?feature1 mfg:requires ?op1 .
    ?op1 mfg:uses ?tool .
    ?tool mfg:name ?toolName .

    ?otherFeature mfg:requires ?op2 .
    ?op2 mfg:uses ?tool .
    ?otherFeature mfg:name ?otherFeatureName .
    FILTER (?otherFeature != ?feature1) .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What materials are removed by operations on cylinder features?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?materialName
WHERE {
    ?feature rdf:type mfg:Feature .
    ?feature mfg:name ?featureName .
    FILTER (CONTAINS(LCASE(?featureName), "cylinder")) .
    ?feature mfg:requires ?operation .
    ?operation mfg:removes ?material .
    ?material mfg:name ?materialName .
}""",
        "expected_nonempty": True
    },
    {
        "question": "List all operations with their tools and machines.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?opName ?toolName ?machineName
WHERE {
    ?operation rdf:type mfg:Operation .
    ?operation mfg:name ?opName .
    ?operation mfg:uses ?tool .
    ?tool mfg:name ?toolName .
    ?operation mfg:runsOn ?machine .
    ?machine mfg:name ?machineName .
}""",
        "expected_nonempty": True
    },
    {
        "question": "What is the total number of triples in the knowledge graph?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT (COUNT(?s) AS ?tripleCount)
WHERE {
    ?s ?p ?o .
}""",
        "expected_nonempty": True
    },
    {
        "question": "Find features that require multiple operations.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?feature ?featureName (COUNT(?operation) AS ?opCount)
WHERE {
    ?feature rdf:type mfg:Feature .
    ?feature mfg:name ?featureName .
    ?feature mfg:requires ?operation .
} GROUP BY ?feature ?featureName
HAVING (COUNT(?operation) > 1)""",
        "expected_nonempty": True
    },
    {
        "question": "What operations are performed on steel material?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?operation ?opName
WHERE {
    ?operation rdf:type mfg:Operation .
    ?operation mfg:name ?opName .
    ?operation mfg:removes ?material .
    ?material mfg:name ?materialName .
    FILTER (CONTAINS(LCASE(?materialName), "steel")) .
}""",
        "expected_nonempty": True
    },
    {
        "question": "Generate a complete manufacturing report with features, operations, tools, and machines.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?featureName ?opName ?toolName ?machineName ?materialName
WHERE {
    ?feature rdf:type mfg:Feature .
    ?feature mfg:name ?featureName .
    ?feature mfg:requires ?operation .
    ?operation mfg:name ?opName .
    ?operation mfg:uses ?tool .
    ?tool mfg:name ?toolName .
    ?operation mfg:runsOn ?machine .
    ?machine mfg:name ?machineName .
    ?operation mfg:removes ?material .
    ?material mfg:name ?materialName .
} ORDER BY ?featureName ?opName""",
        "expected_nonempty": True
    },

    # === Parameter-provenance queries (51-54, Revision 3) ===
    # Each KEFC parameter record of every plan step is an RDF resource
    # mfg:param_<step>_<name> (rdf_triplestore.add_parameter_record).
    {
        "question": "Which rule and ontology sources produced the spindle speed of step 3?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?value ?unit ?ruleId ?ontologySource
WHERE {
    ?step mfg:nodeType "operation_instance" .
    ?step mfg:stepNumber ?n .
    FILTER (?n = 3)
    ?step mfg:hasParameterRecord ?p .
    ?p mfg:parameterName "spindle_speed" .
    ?p mfg:value ?value .
    ?p mfg:unit ?unit .
    ?p mfg:ruleId ?ruleId .
    ?p mfg:ontologySource ?ontologySource .
}""",
        "expected_nonempty": True
    },
    {
        "question": "How many parameter records have a rule identifier and at least one ontology source?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT (COUNT(DISTINCT ?p) AS ?records)
WHERE {
    ?p a mfg:ParameterRecord .
    ?p mfg:ruleId ?ruleId .
    FILTER EXISTS { ?p mfg:ontologySource ?source }
}
HAVING (COUNT(DISTINCT ?p) > 0)""",
        "expected_nonempty": True
    },
    {
        "question": "Which parameter records lack a rule identifier or an ontology source?",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?p
WHERE {
    ?p a mfg:ParameterRecord .
    FILTER (NOT EXISTS { ?p mfg:ruleId ?r } || NOT EXISTS { ?p mfg:ontologySource ?s })
}""",
        "expected_nonempty": False
    },
    {
        "question": "List all parameters of approved steps with value, unit and rule.",
        "sparql": """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?stepNumber ?name ?value ?unit ?ruleId
WHERE {
    ?step mfg:nodeType "operation_instance" .
    ?step mfg:validationStatus ?status .
    FILTER (?status IN ("auto_approved", "expert_approved"))
    ?step mfg:stepNumber ?stepNumber .
    ?step mfg:hasParameterRecord ?p .
    ?p mfg:parameterName ?name .
    ?p mfg:value ?value .
    ?p mfg:unit ?unit .
    ?p mfg:ruleId ?ruleId .
} ORDER BY ?stepNumber ?name""",
        "expected_nonempty": True
    }
]

def get_examples_by_category(category: str) -> List[Dict[str, str]]:
    """
    Get examples filtered by category.
    
    Args:
        category: Category name (feature, operation, tool, sequence, complex)
        
    Returns:
        List of example dicts for the category
    """
    category_ranges = {
        "feature": (0, 10),
        "operation": (10, 20),
        "tool": (20, 30),
        "sequence": (30, 40),
        "complex": (40, 50)
    }
    
    if category not in category_ranges:
        raise ValueError(f"Unknown category: {category}. Use one of: {list(category_ranges.keys())}")
    
    start, end = category_ranges[category]
    return EXAMPLES[start:end]

# ---------------------------------------------------------------------------
# Fixed-order evaluation suite (Revision 3). main.py runs all 50 examples, in
# file order, at every invocation; the expected outcome of each query is
# stated per configuration, so a correct empty answer counts as a pass and an
# unexpected non-empty answer counts as a failure.

CATEGORY_RANGES = (
    (1, 10, "feature"), (11, 20, "operation"), (21, 30, "tool"),
    (31, 40, "sequence"), (41, 50, "complex"), (51, 54, "provenance"),
)

# Q52: the run-time assertion in main.py requires its count to equal four
# parameter records (feed, spindle speed, depth of cut, coolant) per planned
# step.
PROVENANCE_COUNT_QUERY_INDEX = 52

# Queries whose correct answer is empty for this case in every configuration.
EXPECTED_EMPTY = {
    7: "no feature of the case has a diameter above 50 mm (largest 24.95 mm)",
    19: "no threading operation is modelled in machining_process.owl",
    30: "no tool geometry in tools.owl contains '35'",
    36: "no threading operation is modelled, so nothing precedes one",
    53: "every parameter record carries a rule identifier and at least one ontology source",
}

# Queries whose answer depends on the run configuration: non-empty exactly
# when the configuration key has the stated value, empty otherwise.
EXPECTED_NONEMPTY_IF = {
    14: ("material", "steel_1045"),   # 'Which operations remove steel_1045 material?'
    49: ("material", "steel_1045"),   # 'What operations are performed on steel material?'
    20: ("machine", "cnc_lathe"),     # 'Find operations that run on CNC lathe.'
}


def example_category(index: int) -> str:
    for lo, hi, name in CATEGORY_RANGES:
        if lo <= index <= hi:
            return name
    return "unknown"


def expected_nonempty(index: int, context: Dict[str, Any]) -> bool:
    """Expected outcome of query `index` (1-based) for a run configuration
    context = {'material': ..., 'machine': ...}: True if the correct answer
    has at least one row, False if the correct answer is empty."""
    if index in EXPECTED_EMPTY:
        return False
    if index in EXPECTED_NONEMPTY_IF:
        key, value = EXPECTED_NONEMPTY_IF[index]
        return context.get(key) == value
    return True


def get_full_suite() -> List[Dict[str, Any]]:
    """All examples in file order, each with its 1-based index and category."""
    return [dict(ex, index=i, category=example_category(i)) for i, ex in enumerate(EXAMPLES, 1)]


def get_random_examples(count: int = 5) -> List[Dict[str, str]]:
    """
    Get random examples for few-shot learning.
    
    Args:
        count: Number of random examples to return
        
    Returns:
        List of random example dicts
    """
    import random
    return random.sample(EXAMPLES, min(count, len(EXAMPLES)))

def validate_examples() -> Dict[str, Any]:
    """
    Validate all examples have required fields.
    
    Returns:
        Dict with validation results
    """
    results = {
        "total": len(EXAMPLES),
        "valid": 0,
        "invalid": [],
        "categories": {
            "feature": 0,
            "operation": 0,
            "tool": 0,
            "sequence": 0,
            "complex": 0
        }
    }
    
    for i, example in enumerate(EXAMPLES):
        if "question" not in example or "sparql" not in example:
            results["invalid"].append(f"Example {i+1}: missing 'question' or 'sparql' field")
        else:
            results["valid"] += 1
            
            # Categorize
            if i < 10:
                results["categories"]["feature"] += 1
            elif i < 20:
                results["categories"]["operation"] += 1
            elif i < 30:
                results["categories"]["tool"] += 1
            elif i < 40:
                results["categories"]["sequence"] += 1
            else:
                results["categories"]["complex"] += 1
    
    return results
