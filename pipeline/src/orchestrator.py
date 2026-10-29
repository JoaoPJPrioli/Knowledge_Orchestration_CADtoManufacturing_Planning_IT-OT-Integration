"""
GraphRAG Orchestrator Module
============================
Query-engine layer bridging the manufacturing knowledge graph with natural-language
queries and SPARQL — used in production only as `main.py`'s SPARQL query-engine handle
(`ManufacturingOrchestrator.set_triplestore()` + `QueryEngine`). Plan generation itself
now lives in `kefc_controller.py` (KEFC), grounded in SKL's reasoned facts rather than
`ontology.py`'s dicts — see AGENTS.md / .codex/architecture.md.

Adapted from the Disassembly_KG_Platform's rag/engine.py architecture:
- Zero-hallucination policy: all answers grounded in KG facts
- Schema-aware queries: KG schema guides query construction
- Multi-hop reasoning: traverse feature → operation → tool → parameter chains

Key Classes:
- SchemaDescriber: Dynamic KG schema descriptions for query grounding
- QueryEngine: NetworkX/SPARQL-based query execution (replaces Cypher/Neo4j)
- ManufacturingOrchestrator: thin coordinator around QueryEngine + optional
  natural-language/export helpers over a plan a caller supplies directly
  (`self.manufacturing_plan`), rather than generating one itself
"""

import json
import re
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict
from datetime import datetime

# Import KG modules
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class SchemaDescriber:
    """
    Dynamic schema description for the manufacturing KG.
    
    Provides natural language descriptions of KG structure to guide
    query construction and ensure zero-hallucination responses.
    """
    
    SCHEMA_DESCRIPTION = """
    Manufacturing Knowledge Graph Schema:
    
    Node Types:
    - Feature: Geometric features extracted from CAD (Hole, Step, Chamfer, Boss, etc.)
      Properties: id, type, description, absolute_location, dimensions, orientation, tolerance
    
    - Operation: Manufacturing operations (Turning, Drilling, Counterboring, etc.)
      Properties: name, description, parameters, g_codes, cycle_codes
    
    - Tool: Cutting tools (Drill Bit, Turning Insert, Counterbore Cutter, etc.)
      Properties: name, type, material, geometry, recommended_operations
    
    - Machine: CNC machines (CNC Lathe, CNC Mill, etc.)
      Properties: name, model, capabilities, supported_operations, safety_limits
    
    - Material: Workpiece materials (Steel, Aluminum, Stainless Steel, etc.)
      Properties: name, type, properties, cutting_parameters, machinability_rating
    
    - Parameter: Dimensional or location parameters
      Properties: parameter_type, key, value, coordinates
    
    Edge Types:
    - REQUIRES: Feature requires Operation (e.g., Blind Hole → Drilling)
    - USES: Operation uses Tool (e.g., Drilling → Drill Bit)
    - RUNS_ON: Operation runs on Machine (e.g., Drilling → CNC Lathe)
    - REMOVES: Operation removes Material (e.g., Turning → Steel)
    - SEQUENCE_BEFORE: Operation precedes another (e.g., Rough Turning → Finish Turning)
    - HAS_DIMENSION: Feature has dimensional Parameter
    - LOCATED_AT: Feature is located at Coordinate Parameter
    """
    
    @classmethod
    def get_schema_summary(cls) -> str:
        """Get a concise schema summary for query grounding."""
        return cls.SCHEMA_DESCRIPTION.strip()
    
    @classmethod
    def get_node_type_description(cls, node_type: str) -> str:
        """Get description for a specific node type."""
        descriptions = {
            'feature': 'Geometric features extracted from CAD models',
            'operation': 'Manufacturing operations (turning, drilling, milling, etc.)',
            'tool': 'Cutting tools with geometry and material specifications',
            'machine': 'CNC machines with capabilities and safety limits',
            'material': 'Workpiece materials with cutting parameters',
            'parameter': 'Dimensional or location parameters'
        }
        return descriptions.get(node_type, 'Unknown node type')
    
    @classmethod
    def get_edge_type_description(cls, edge_type: str) -> str:
        """Get description for a specific edge type."""
        descriptions = {
            'REQUIRES': 'Feature requires this manufacturing operation',
            'USES': 'Operation uses this cutting tool',
            'RUNS_ON': 'Operation runs on this machine',
            'REMOVES': 'Operation removes this material',
            'SEQUENCE_BEFORE': 'Operation precedes another in the machining sequence',
            'HAS_DIMENSION': 'Feature has this dimensional parameter',
            'LOCATED_AT': 'Feature is located at these coordinates'
        }
        return descriptions.get(edge_type, 'Unknown relationship type')


class QueryEngine:
    """
    NetworkX-based query engine for the manufacturing KG.
    
    Replaces Cypher/Neo4j queries with NetworkX graph traversals.
    Supports multi-hop queries for feature → operation → tool → parameter chains.
    """
    
    def __init__(self, kg, triplestore=None):
        """
        Initialize query engine with a ManufacturingKG instance.
        
        Args:
            kg: ManufacturingKG instance with built graph
            triplestore: Optional ManufacturingTriplestore for SPARQL queries
        """
        self.kg = kg
        self.G = kg.G
        self.triplestore = triplestore
        self._backend = 'networkx'  # Default backend
        
        if triplestore:
            self._backend = 'sparql'
            print(f"  ✓ QueryEngine initialized with SPARQL backend")
    
    def query_operations_for_feature(self, feature_id: int) -> List[Dict]:
        """
        Query: What operations are required for feature N?

        REQUIRES targets are operation-INSTANCE nodes (one per planned
        step), not the shared operation-type vocabulary node — resolved back
        to the type node here for the descriptive fields, plus the
        instance's own step_number/tool_id/validation_status.

        Args:
            feature_id: Feature identifier

        Returns:
            List of operation dictionaries
        """
        feature_node = f"feature_{feature_id}"

        if not self.G.has_node(feature_node):
            return []

        operations = []

        # Traverse REQUIRES edges: Feature → Operation instance
        for neighbor in self.G.successors(feature_node):
            edge_data = self.G[feature_node][neighbor]

            if edge_data.get('relationship') == 'REQUIRES':
                instance_data = self.G.nodes[neighbor]
                type_node = f"op_{instance_data.get('operation_type')}"
                op_data = self.G.nodes[type_node] if self.G.has_node(type_node) else {}
                operations.append({
                    'operation_id': instance_data.get('operation_type'),
                    'operation_name': op_data.get('name'),
                    'description': op_data.get('description'),
                    'parameters': op_data.get('parameters', {}),
                    'g_codes': op_data.get('g_codes', []),
                    'cycle_codes': op_data.get('cycle_codes', []),
                    'instance_id': neighbor,
                    'step_number': instance_data.get('step_number'),
                    'tool_id': instance_data.get('tool_id'),
                    'validation_status': instance_data.get('validation_status'),
                })

        return operations

    def query_tool_for_operation(self, operation_id: str) -> Dict:
        """
        Query: What tool is used for operation X?

        Accepts either a type-level operation id (e.g. "rough_turning") or a
        specific step's instance id (e.g. "opstep_3"). For a type-level id,
        since one operation type can back multiple planned steps, this
        returns the first matching instance's tool — pass an instance_id
        (see query_operations_for_feature's returned 'instance_id') for a
        specific step's tool.

        Args:
            operation_id: Operation type id or operation-instance id

        Returns:
            Tool dictionary
        """
        op_node = operation_id if operation_id.startswith('opstep_') else f"op_{operation_id}"

        if not self.G.has_node(op_node):
            return {}

        if self.G.nodes[op_node].get('node_type') == 'operation':
            op_node = next(
                (n for n, data in self.G.nodes(data=True)
                 if data.get('node_type') == 'operation_instance'
                 and data.get('operation_type') == operation_id),
                None,
            )
            if op_node is None:
                return {}

        # Traverse USES edges: Operation → Tool
        for neighbor in self.G.successors(op_node):
            edge_data = self.G[op_node][neighbor]

            if edge_data.get('relationship') == 'USES':
                tool_data = self.G.nodes[neighbor]
                return {
                    'tool_id': tool_data.get('id'),
                    'tool_name': tool_data.get('name'),
                    'type': tool_data.get('type'),
                    'material': tool_data.get('material'),
                    'geometry': tool_data.get('geometry'),
                    'recommended_operations': tool_data.get('recommended_operations', [])
                }

        return {}

    def query_machining_sequence(self) -> List[Dict]:
        """
        Query: What is the optimal machining sequence?

        `operation_from`/`operation_to` are operation-INSTANCE ids (e.g.
        "opstep_3") — every consecutive step-to-step transition is now
        represented (previously dropped between same-type steps). Values are
        shown as their operation_type for readability, matching this
        method's pre-existing (legacy-id, prefix-stripped) output shape.

        Returns:
            List of operation steps in sequence order
        """
        sequence = []

        # Find all SEQUENCE_BEFORE edges
        for u, v, data in self.G.edges(data=True):
            if data.get('relationship') == 'SEQUENCE_BEFORE':
                sequence.append({
                    'step_from': data.get('step_from'),
                    'step_to': data.get('step_to'),
                    'operation_from': self.G.nodes[u].get('operation_type', u),
                    'operation_to': self.G.nodes[v].get('operation_type', v)
                })

        # Sort by step number
        sequence.sort(key=lambda x: x['step_from'])

        return sequence
    
    def query_feature_details(self, feature_id: int) -> Dict:
        """
        Query: What are the details of feature N?
        
        Args:
            feature_id: Feature identifier
            
        Returns:
            Feature details dictionary
        """
        feature_node = f"feature_{feature_id}"
        
        if not self.G.has_node(feature_node):
            return {}
        
        feature_data = self.G.nodes[feature_node]
        
        # Get dimensions from HAS_DIMENSION edges
        dimensions = {}
        for neighbor in self.G.successors(feature_node):
            edge_data = self.G[feature_node][neighbor]
            
            if edge_data.get('relationship') == 'HAS_DIMENSION':
                dim_data = self.G.nodes[neighbor]
                dim_key = dim_data.get('key', '')
                dim_value = dim_data.get('value', '')
                dimensions[dim_key] = dim_value
        
        # Get location from LOCATED_AT edges
        location = {}
        for neighbor in self.G.successors(feature_node):
            edge_data = self.G[feature_node][neighbor]
            
            if edge_data.get('relationship') == 'LOCATED_AT':
                loc_data = self.G.nodes[neighbor]
                location = loc_data.get('coordinates', {})
                break
        
        return {
            'id': feature_data.get('id'),
            'type': feature_data.get('type'),
            'description': feature_data.get('description', ''),
            'dimensions': dimensions,
            'location': location,
            'orientation': feature_data.get('orientation', ''),
            'tolerance': feature_data.get('tolerance', 'General')
        }
    
    def query_multi_hop(self, feature_id: int) -> Dict:
        """
        Multi-hop query: Feature → Operations → Tools → Parameters
        
        Args:
            feature_id: Feature identifier
            
        Returns:
            Complete manufacturing information for the feature
        """
        result = {
            'feature_id': feature_id,
            'feature_details': self.query_feature_details(feature_id),
            'operations': [],
            'tools': []
        }
        
        # Get operations
        operations = self.query_operations_for_feature(feature_id)
        result['operations'] = operations
        
        # Get tools for each operation
        tools_seen = set()
        for op in operations:
            tool = self.query_tool_for_operation(op['operation_id'])
            if tool and tool['tool_id'] not in tools_seen:
                result['tools'].append(tool)
                tools_seen.add(tool['tool_id'])
        
        return result
    
    def query_all_features_summary(self) -> List[Dict]:
        """
        Query: Summary of all features and their operations.
        
        Returns:
            List of feature summaries
        """
        summaries = []
        
        # Find all feature nodes
        feature_nodes = [
            node for node, data in self.G.nodes(data=True)
            if data.get('node_type') == 'feature'
        ]
        
        for feature_node in feature_nodes:
            # Extract feature ID from node name
            feature_id = int(feature_node.replace('feature_', ''))
            
            summary = self.query_multi_hop(feature_id)
            summaries.append(summary)
        
        return summaries
    
    def set_triplestore(self, triplestore):
        """Set RDF triplestore for SPARQL queries."""
        self.triplestore = triplestore
        self._backend = 'sparql'
        print(f"  ✓ Triplestore set, switching to SPARQL backend")
    
    def switch_backend(self, backend: str):
        """
        Switch query backend between NetworkX and SPARQL.
        
        Args:
            backend: 'networkx' or 'sparql'
        """
        if backend not in ['networkx', 'sparql']:
            raise ValueError(f"Unknown backend: {backend}. Use 'networkx' or 'sparql'")
        
        if backend == 'sparql' and not self.triplestore:
            raise ValueError("No triplestore set. Call set_triplestore() first.")
        
        self._backend = backend
        print(f"  ✓ Switched to {backend.upper()} backend")
    
    def query_operations_for_feature_sparql(self, feature_id: int) -> List[Dict]:
        """
        Query operations for feature using SPARQL.

        `?feature mfg:requires ?operation` now binds `?operation` to a
        per-step operation-INSTANCE individual (see
        ManufacturingTriplestore.add_operation_instance) rather than the
        shared operation-type individual — it still carries its own
        mfg:name/mfg:description (copied from its type at creation), so this
        query is otherwise unchanged.

        Args:
            feature_id: Feature identifier

        Returns:
            List of operation dictionaries
        """
        if not self.triplestore:
            raise ValueError("No triplestore available for SPARQL queries")

        sparql_query = f"""PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?operation ?opName ?opDescription
WHERE {{
    ?feature mfg:id "feature_{feature_id}" .
    ?feature mfg:requires ?operation .
    ?operation mfg:name ?opName .
    OPTIONAL {{ ?operation mfg:description ?opDescription }} .
}}"""
        
        results = self.triplestore.execute_sparql(sparql_query)
        
        operations = []
        for row in results:
            operations.append({
                'operation_id': str(row[0]),
                'operation_name': str(row[1]),
                'description': str(row[2]) if len(row) > 2 else '',
                'parameters': {},
                'g_codes': [],
                'cycle_codes': []
            })
        
        return operations
    
    def query_tool_for_operation_sparql(self, operation_id: str) -> Dict:
        """
        Query tool for operation using SPARQL.
        
        Args:
            operation_id: Operation identifier
            
        Returns:
            Tool dictionary
        """
        if not self.triplestore:
            raise ValueError("No triplestore available for SPARQL queries")
        
        sparql_query = f"""PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?toolName ?toolType ?toolMaterial ?toolGeometry
WHERE {{
    ?operation mfg:id "op_{operation_id}" .
    ?operation mfg:uses ?tool .
    ?tool mfg:name ?toolName .
    OPTIONAL {{ ?tool mfg:type ?toolType }} .
    OPTIONAL {{ ?tool mfg:material ?toolMaterial }} .
    OPTIONAL {{ ?tool mfg:geometry ?toolGeometry }} .
}}"""
        
        results = self.triplestore.execute_sparql(sparql_query)
        
        if not results:
            return {}
        
        row = results[0]
        return {
            'tool_id': operation_id,
            'tool_name': str(row[0]),
            'type': str(row[1]) if len(row) > 1 else '',
            'material': str(row[2]) if len(row) > 2 else '',
            'geometry': str(row[3]) if len(row) > 3 else '',
            'recommended_operations': []
        }
    
    def query_machining_sequence_sparql(self) -> List[Dict]:
        """
        Query machining sequence using SPARQL.
        
        Returns:
            List of operation steps in sequence order
        """
        if not self.triplestore:
            raise ValueError("No triplestore available for SPARQL queries")
        
        sparql_query = """PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?opFrom ?opTo ?opFromName ?opToName
WHERE {
    ?opFrom mfg:sequenceBefore ?opTo .
    ?opFrom mfg:id ?opFrom .
    ?opTo mfg:id ?opTo .
    OPTIONAL { ?opFrom mfg:name ?opFromName } .
    OPTIONAL { ?opTo mfg:name ?opToName } .
}"""
        
        results = self.triplestore.execute_sparql(sparql_query)
        
        sequence = []
        for row in results:
            sequence.append({
                'step_from': str(row[0]),
                'step_to': str(row[1]),
                'operation_from': str(row[2]) if len(row) > 2 else '',
                'operation_to': str(row[3]) if len(row) > 3 else ''
            })
        
        return sequence
    
    def query_feature_details_sparql(self, feature_id: int) -> Dict:
        """
        Query feature details using SPARQL.
        
        Args:
            feature_id: Feature identifier
            
        Returns:
            Feature details dictionary
        """
        if not self.triplestore:
            raise ValueError("No triplestore available for SPARQL queries")
        
        sparql_query = f"""PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?featureName ?featureDescription ?dimKey ?dimValue ?coordinates
WHERE {{
    ?feature mfg:id "feature_{feature_id}" .
    OPTIONAL {{ ?feature mfg:name ?featureName }} .
    OPTIONAL {{ ?feature mfg:description ?featureDescription }} .
    OPTIONAL {{
        ?feature mfg:hasDimension ?dimension .
        ?dimension mfg:dimensionKey ?dimKey .
        ?dimension mfg:value ?dimValue .
    }} .
    OPTIONAL {{
        ?feature mfg:locatedAt ?location .
        ?location mfg:coordinates ?coordinates .
    }} .
}}"""
        
        results = self.triplestore.execute_sparql(sparql_query)
        
        if not results:
            return {}
        
        # Process results
        feature_data = {
            'id': feature_id,
            'type': '',
            'description': '',
            'dimensions': {},
            'location': {},
            'orientation': '',
            'tolerance': 'General'
        }
        
        for row in results:
            if len(row) > 0 and row[0]:
                feature_data['type'] = str(row[0])
            if len(row) > 1 and row[1]:
                feature_data['description'] = str(row[1])
            if len(row) > 2 and row[2]:
                dim_key = str(row[2])
                dim_value = str(row[3]) if len(row) > 3 and row[3] else ''
                feature_data['dimensions'][dim_key] = dim_value
            if len(row) > 4 and row[4]:
                feature_data['location'] = {'coordinates': str(row[4])}
        
        return feature_data
    
    def query_multi_hop_sparql(self, feature_id: int) -> Dict:
        """
        Multi-hop query using SPARQL: Feature → Operations → Tools → Parameters
        
        Args:
            feature_id: Feature identifier
            
        Returns:
            Complete manufacturing information for the feature
        """
        if not self.triplestore:
            raise ValueError("No triplestore available for SPARQL queries")
        
        sparql_query = f"""PREFIX mfg: <http://onto.brep.org/manufacturing#>

SELECT ?opName ?toolName ?machineName ?dimKey ?dimValue
WHERE {{
    ?feature mfg:id "feature_{feature_id}" .
    ?feature mfg:requires ?operation .
    ?operation mfg:name ?opName .
    ?operation mfg:uses ?tool .
    ?tool mfg:name ?toolName .
    ?operation mfg:runsOn ?machine .
    ?machine mfg:name ?machineName .
    OPTIONAL {{
        ?feature mfg:hasDimension ?dimension .
        ?dimension mfg:dimensionKey ?dimKey .
        ?dimension mfg:value ?dimValue .
    }} .
}}"""
        
        results = self.triplestore.execute_sparql(sparql_query)
        
        result = {
            'feature_id': feature_id,
            'feature_details': self.query_feature_details_sparql(feature_id),
            'operations': [],
            'tools': []
        }
        
        tools_seen = set()
        for row in results:
            op_name = str(row[0]) if len(row) > 0 and row[0] else ''
            tool_name = str(row[1]) if len(row) > 1 and row[1] else ''
            
            if op_name and op_name not in [op['operation_name'] for op in result['operations']]:
                result['operations'].append({
                    'operation_id': op_name.replace(' ', '_').lower(),
                    'operation_name': op_name,
                    'description': '',
                    'parameters': {},
                    'g_codes': [],
                    'cycle_codes': []
                })
            
            if tool_name and tool_name not in tools_seen:
                result['tools'].append({
                    'tool_id': tool_name.replace(' ', '_').lower(),
                    'tool_name': tool_name,
                    'type': '',
                    'material': '',
                    'geometry': '',
                    'recommended_operations': []
                })
                tools_seen.add(tool_name)
        
        return result
    
    def query_with_backend(self, query_name: str, *args, **kwargs):
        """
        Execute query using the current backend (NetworkX or SPARQL).
        
        Args:
            query_name: Query method name
            *args: Positional arguments for the query
            **kwargs: Keyword arguments for the query
            
        Returns:
            Query results
        """
        if self._backend == 'sparql':
            sparql_method = getattr(self, f"{query_name}_sparql", None)
            if sparql_method:
                return sparql_method(*args, **kwargs)
            else:
                raise ValueError(f"No SPARQL implementation for query: {query_name}")
        else:
            # Use NetworkX backend
            method = getattr(self, query_name, None)
            if method:
                return method(*args, **kwargs)
            else:
                raise ValueError(f"Unknown query method: {query_name}")


class ManufacturingOrchestrator:
    """
    Query-engine coordinator for the manufacturing knowledge graph. Does not
    generate a manufacturing plan itself (that's KEFC's job — see
    kefc_controller.py) — a caller sets `self.manufacturing_plan` directly if
    it wants the natural-language/export helpers below to have something to
    describe.

    Key Methods:
    - ingest_features: Load features into the orchestrator
    - get_natural_language_plan: Generate human-readable plan description
      (from self.manufacturing_plan, however it was set)
    - get_operation_for_feature: Query operations for a specific feature
    - get_tool_recommendations: Get tool recommendations for operations
    """
    
    def __init__(self, kg=None):
        """
        Initialize orchestrator with optional KG.
        
        Args:
            kg: ManufacturingKG instance (optional, can be set later)
        """
        self.kg = kg
        self.query_engine = QueryEngine(kg) if kg else None
        self.features = []
        self.manufacturing_plan = []
        self.plan_metadata = {}
    
    def set_kg(self, kg):
        """Set the knowledge graph after initialization."""
        self.kg = kg
        self.query_engine = QueryEngine(kg)

    def set_triplestore(self, triplestore):
        """Set the RDF triplestore for SPARQL-backed querying."""
        self.triplestore = triplestore
        if self.kg is not None:
            self.query_engine = QueryEngine(self.kg, triplestore)
        elif self.query_engine is not None:
            self.query_engine.set_triplestore(triplestore)
        print("  ✓ Triplestore set on orchestrator")

    def ingest_features(self, features: List[Dict]):
        """
        Ingest parsed features into the orchestrator.
        
        Args:
            features: List of feature dictionaries from feature_parser
        """
        self.features = features
        print(f"  ✓ Ingested {len(features)} features")
    
    # generate_manufacturing_plan() (the only method here that called into
    # ontology.py, via get_machining_sequence) was removed when ontology.py
    # was retired — never invoked in production anyway (main()'s one
    # production use of ManufacturingOrchestrator is as a SPARQL query-engine
    # handle, not for plan generation; see AGENTS.md / .codex/architecture.md).
    # The methods below (_generate_semantic_annotations,
    # get_natural_language_plan, export_plan, get_plan_summary, etc.) are kept
    # — they're generic and still work off self.manufacturing_plan/self.features,
    # which a caller can populate directly (e.g. from KEFC's plan) without
    # needing this class to generate it.

    def _generate_semantic_annotations(
        self,
        operation_id: str,
        feature_type: str,
        tool: Dict
    ) -> Dict:
        """
        Generate semantic annotations for a manufacturing step.
        
        These annotations provide natural language descriptions
        grounded in KG facts (zero-hallucination policy).
        
        Args:
            operation_id: Operation identifier
            feature_type: Feature type
            tool: Tool dictionary
            
        Returns:
            Dict with semantic annotations
        """
        # Get schema descriptions
        op_description = SchemaDescriber.get_node_type_description('operation')
        tool_description = SchemaDescriber.get_node_type_description('tool')
        
        # Generate natural language description
        feature_desc = f"A {feature_type.replace('_', ' ')} feature"
        operation_desc = f"requires {operation_id.replace('_', ' ')} operation"
        tool_desc = f"using {tool.get('tool_name', 'appropriate tool')}"
        
        return {
            'description': f"{feature_desc} {operation_desc} {tool_desc}",
            'operation_context': op_description,
            'tool_context': tool_description,
            'kg_grounded': True
        }
    
    def _count_feature_types(self) -> Dict[str, int]:
        """Count features by type."""
        counts = defaultdict(int)
        for feature in self.features:
            feature_type = feature.get('type', 'unknown')
            counts[feature_type] += 1
        return dict(counts)
    
    def _count_operation_types(self) -> Dict[str, int]:
        """Count operations by type in the manufacturing plan."""
        counts = defaultdict(int)
        for step in self.manufacturing_plan:
            operation = step.get('operation', 'unknown')
            counts[operation] += 1
        return dict(counts)
    
    def _get_tools_used(self) -> List[str]:
        """Get list of unique tools used in the manufacturing plan."""
        tools = set()
        for step in self.manufacturing_plan:
            tool_id = step.get('tool_id')
            if tool_id:
                tools.add(tool_id)
        return list(tools)
    
    def get_natural_language_plan(self) -> str:
        """
        Generate a human-readable natural language description of the plan.
        
        Returns:
            String with natural language manufacturing plan
        """
        if not self.manufacturing_plan:
            return "No manufacturing plan generated yet."
        
        lines = []
        lines.append("=" * 70)
        lines.append("Manufacturing Plan: Motor Shaft (Eixo)")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"Material: {self.plan_metadata.get('material', 'N/A')}")
        lines.append(f"Machine: {self.plan_metadata.get('machine', 'N/A')}")
        lines.append(f"Total Features: {self.plan_metadata.get('total_features', 0)}")
        lines.append(f"Total Operations: {self.plan_metadata.get('total_steps', 0)}")
        lines.append("")
        lines.append("-" * 70)
        lines.append("Manufacturing Sequence:")
        lines.append("-" * 70)
        
        for step in self.manufacturing_plan:
            lines.append("")
            lines.append(f"Step {step['step_number']}: {step['operation_name']}")
            lines.append(f"  Feature: {step['feature_id']} ({step['feature_type']})")
            lines.append(f"  Tool: {step.get('tool_id') or 'N/A'}")
            lines.append(f"  Machine: {step.get('machine', 'N/A')}")

            if step.get('validation_status') and step['validation_status'] != 'auto_approved':
                lines.append(f"  Status: {step['validation_status']}")
        
        lines.append("")
        lines.append("=" * 70)
        
        return "\n".join(lines)
    
    def get_operation_for_feature(self, feature_id: int) -> Dict:
        """
        Query operations for a specific feature.
        
        Args:
            feature_id: Feature identifier
            
        Returns:
            Dict with feature operations and tools
        """
        return self.query_engine.query_multi_hop(feature_id)
    
    def get_tool_recommendations(self, operation_id: str) -> Dict:
        """
        Get tool recommendations for an operation.
        
        Args:
            operation_id: Operation identifier
            
        Returns:
            Tool recommendation dictionary
        """
        return self.query_engine.query_tool_for_operation(operation_id)
    
    def export_plan(self, filepath: str) -> str:
        """
        Export manufacturing plan to JSON.
        
        Args:
            filepath: Path to save JSON file
            
        Returns:
            JSON string
        """
        export_data = {
            'metadata': self.plan_metadata,
            'plan': self.manufacturing_plan,
            'natural_language_description': self.get_natural_language_plan()
        }
        
        json_str = json.dumps(export_data, indent=2, default=str)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(json_str)
        
        return json_str
    
    def get_plan_summary(self) -> Dict:
        """
        Get a summary of the manufacturing plan.
        
        Returns:
            Dict with plan summary statistics
        """
        return self.plan_metadata
