"""
Knowledge Graph Builder Module
==============================
Builds a Manufacturing Knowledge Graph using NetworkX with feature, operation,
tool, machine, and material nodes connected by semantic relationships.

Adapted from the Disassembly_KG_Platform's 3-stage KG construction pattern:
1. Structural foundation (nodes and basic relationships)
2. Operational enrichment (operation sequences and dependencies)
3. Property enrichment (parameters, constraints, and metadata)

Graph Structure:
- Node types: Feature, Operation, Tool, Machine, Material, Parameter
- Edge types: REQUIRES, USES, HAS_PARAMS, RUNS_ON, REMOVES, SEQUENCE_BEFORE,
              LOCATED_AT, HAS_DIMENSION, CONNECTED_TO
"""

import networkx as nx
import numpy as np
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skl_repository import (
    OWL_OPERATION_TO_LEGACY_ID, OWL_TOOL_TO_LEGACY_ID, MATERIAL_INDIVIDUAL_TO_KEY,
    MACHINE_INDIVIDUAL_TO_KEY,
)


class ManufacturingKG:
    """
    Manufacturing Knowledge Graph builder and query engine.
    
    Provides methods to:
    - Build KG from features and ontology
    - Query operations for features
    - Retrieve tool recommendations
    - Get machining sequences
    - Visualize graph structure
    """
    
    def __init__(self):
        """Initialize an empty directed graph."""
        self.G = nx.DiGraph()
        self.G.name = "Manufacturing_Knowledge_Graph"
        self._node_counters = defaultdict(int)
    
    def _add_feature_nodes(self, features: List[Dict]):
        """Add feature nodes from parsed feature data."""
        for feature in features:
            feature_id = feature['id']
            feature_type = feature['type']
            
            # Create unique node ID
            node_id = f"feature_{feature_id}"
            
            self.G.add_node(
                node_id,
                node_type='feature',
                id=feature_id,
                type=feature_type,
                description=feature.get('description', ''),
                absolute_location=feature.get('absolute_location', {}),
                relative_position=feature.get('relative_position', {}),
                dimensions=feature.get('dimensions', {}),
                orientation=feature.get('orientation', ''),
                tolerance=feature.get('tolerance', 'General')
            )
            
            self._node_counters['feature'] += 1
    
    def build_kg_from_skl(self, features: List[Dict], repo) -> nx.DiGraph:
        """
        Build the unified graph's structural foundation (vocabulary nodes +
        feature nodes) from SKL (`skl_repository.SKLRepository`). This is the
        sole graph-construction path now — the earlier `ontology.py`-driven
        `build_kg()`/`_add_ontology_nodes()`/`_add_relationships()`/
        `_add_sequence_dependencies()` were retired once `ontology.py` itself
        was removed (every field they read had a verified OWL equivalent, and
        production never called them — see AGENTS.md / .codex/architecture.md).

        Only builds nodes — no REQUIRES/USES/RUNS_ON/REMOVES/SEQUENCE_BEFORE
        edges. Call `populate_decisions_from_kefc()` after KEFC produces the
        manufacturing plan to add those, so the graph's *decisions* (not just
        its provenance annotations) are genuinely SKL/KEFC-derived rather
        than duplicated from a static Python mirror of the ontology.

        Args:
            features: KINM's normalized feature dicts
            repo: an SKLRepository (already loaded; reasoning need not have
                run yet — this only reads vocabulary, not inferred facts)
        """
        for op in repo.list_operations():
            legacy_id = OWL_OPERATION_TO_LEGACY_ID.get(op['id'], op['id'])
            self.G.add_node(
                f"op_{legacy_id}",
                node_type='operation',
                id=legacy_id,
                ontology_individual=op['id'],
                name=op['name'],
                description=op['description'],
                # Concrete cutting parameters are now per-(operation,material)
                # facts KEFC resolves per step (see cutting_parameters.owl),
                # not a generic per-operation-type range — kept empty here
                # only so get_operations_for_feature()'s dict indexing below
                # doesn't KeyError for any caller still using that path.
                parameters={},
                g_codes=op['g_codes'],
                cycle_codes=op['cycle_codes'],
                precedence=op['precedence'],
                ontology_sources=op['ontology_sources'],
            )

        for tool in repo.list_tools():
            legacy_id = OWL_TOOL_TO_LEGACY_ID.get(tool['id'], tool['id'])
            self.G.add_node(
                f"tool_{legacy_id}",
                node_type='tool',
                id=legacy_id,
                ontology_individual=tool['id'],
                name=tool['name'],
                type=tool['type'],
                material=tool['material'],
                geometry=tool['geometry'],
                recommended_operations=[
                    OWL_OPERATION_TO_LEGACY_ID.get(o, o) for o in tool['recommended_operations']
                ],
                ontology_sources=tool['ontology_sources'],
            )

        for machine in repo.list_machines():
            # Node named by the machine key, so that a run with more than one
            # declared machine gets one node per machine instead of every
            # machine overwriting a single hard-coded 'machine_cnc_lathe' node.
            machine_key = MACHINE_INDIVIDUAL_TO_KEY.get(machine['id'], machine['id'])
            self.G.add_node(
                f"machine_{machine_key}",
                node_type='machine',
                id=machine_key,
                ontology_individual=machine['id'],
                name=machine['name'],
                model=machine['model'],
                capabilities=machine['capabilities'],
                supported_operations=[
                    OWL_OPERATION_TO_LEGACY_ID.get(o, o) for o in machine['supported_operations']
                ],
                safety_limits=machine['safety_limits'],
                ontology_sources=machine['ontology_sources'],
            )

        # One vocabulary node per material.owl catalog entry (same pattern as
        # operations/tools/machines above) — this is the FULL materials
        # catalog, not the subset "used" by this run. get_graph_stats()'s
        # 'material' count reflects that: it's the catalog size (currently 3:
        # AISI1045Steel, Aluminum6061T6, StainlessSteel304), not a claim that
        # this run's single workpiece is associated with multiple materials.
        for material in repo.list_materials():
            legacy_id = MATERIAL_INDIVIDUAL_TO_KEY.get(material['id'], material['id'])
            self.G.add_node(
                f"material_{legacy_id}",
                node_type='material',
                id=legacy_id,
                ontology_individual=material['id'],
                name=material['name'],
                properties=material['properties'],
                machinability_rating=material['machinability_rating'],
                recommended_coolant=material['recommended_coolant'],
                ontology_sources=material['ontology_sources'],
            )

        self._add_feature_nodes(features)
        return self.G

    def populate_decisions_from_kefc(self, manufacturing_plan: List[Dict], reconciled_features=None):
        """
        Add the unified graph's decision-bearing edges (REQUIRES, USES,
        RUNS_ON, REMOVES, SEQUENCE_BEFORE) from KEFC's manufacturing plan,
        with rule_id/ontology_sources provenance attached at creation —
        replacing the ontology.py-driven `_add_relationships()` /
        `_add_sequence_dependencies()` used by `build_kg()`, and superseding
        the older `add_kefc_provenance()` bolt-on (provenance is no longer a
        second pass over pre-existing edges; it's part of how the edges are
        made).

        Every planned step gets its own operation-INSTANCE node
        (`opstep_<step_number>`, `node_type='operation_instance'`), linked to
        its operation-TYPE vocabulary node (`op_<legacy_id>`, built by
        `build_kg_from_skl()`) via an INSTANCE_OF edge. REQUIRES/USES/
        RUNS_ON/REMOVES/SEQUENCE_BEFORE all attach to the instance node, not
        the shared type node — previously, multiple steps of the same
        operation type collapsed onto one shared `op_` node, which (a) made
        same-feature-same-type steps silently overwrite each other's edge
        attributes (a `DiGraph` stores one attribute dict per (u,v) pair),
        and (b) forced SEQUENCE_BEFORE to skip same-type consecutive steps
        entirely (`if op_from == op_to: continue`) since a self-loop
        wouldn't represent real sequencing — dropping the large majority of
        real step-to-step transitions. Instance nodes never collide, so
        neither problem applies here; every step is fully addressable and
        every consecutive step pair gets a real SEQUENCE_BEFORE edge.

        Call this on a graph built by `build_kg_from_skl()`, after KEFC has
        produced `manufacturing_plan`.

        Args:
            manufacturing_plan: KEFC's plan steps (kefc_controller.py output)
            reconciled_features: SemanticReconciler's ReconciledFeature list,
                for per-feature mapping confidence on REQUIRES edges (falls
                back to 1.0 if not provided)
        """
        confidence_by_feature = {}
        if reconciled_features:
            confidence_by_feature = {rf.feature_id: rf.confidence for rf in reconciled_features}

        instance_node_by_step = {}
        for step in manufacturing_plan:
            feature_node = f"feature_{step['feature_id']}"
            op_type_node = f"op_{step['operation']}"
            if not (self.G.has_node(feature_node) and self.G.has_node(op_type_node)):
                continue

            # name/description are copied from the type node (not just
            # cross-referenced via INSTANCE_OF) so that existing consumers
            # walking REQUIRES -> "the thing name" (e.g. many of
            # sparql_examples.py's queries, written when REQUIRES pointed
            # directly at the type node) keep working unmodified against the
            # instance node now in that position.
            type_data = self.G.nodes[op_type_node]
            instance_node = f"opstep_{step['step_number']}"
            self.G.add_node(
                instance_node,
                node_type='operation_instance',
                operation_type=step['operation'],
                step_number=step['step_number'],
                feature_id=step['feature_id'],
                tool_id=step.get('tool_id'),
                validation_status=step['validation_status'],
                name=type_data.get('name'),
                description=type_data.get('description'),
                # The step's full parameter package (value, unit, rule_id,
                # ontology_sources, source, input_facts per parameter), kept as
                # a node attribute so the RDF export can publish every
                # parameter record; it adds no node or edge to this graph.
                parameters=step.get('parameters', {}),
            )
            self.G.add_edge(instance_node, op_type_node, relationship='INSTANCE_OF')
            instance_node_by_step[step['step_number']] = instance_node

            rule_ids = sorted({
                p['rule_id'] for p in step.get('parameters', {}).values()
                if isinstance(p, dict) and p.get('rule_id')
            })
            ontology_sources = sorted({
                src for p in step.get('parameters', {}).values()
                if isinstance(p, dict) for src in p.get('ontology_sources', [])
            })
            facts = []
            if rule_ids:
                facts.append('inferredByRule')
            if ontology_sources:
                facts.append('derivedFromOntology')
            if step['validation_status'] == 'requires_review':
                facts.append('requiresExpertValidation')

            self.G.add_edge(
                feature_node, instance_node,
                relationship='REQUIRES',
                confidence=confidence_by_feature.get(step['feature_id'], 1.0),
                # rule_ids/ontology_sources here are the CUTTING-PARAMETER
                # rule provenance (per step['parameters']) — kept for
                # backward compatibility with existing consumers of this
                # edge. operation_rule_id/operation_ontology_sources below
                # are the OPERATION decision's own provenance (why this
                # operation was selected for this feature), separate from
                # why its parameters were selected — see kefc_controller.py's
                # _build_step, which now threads both through.
                rule_ids=rule_ids,
                ontology_sources=ontology_sources,
                operation_rule_id=step.get('operation_selection_rule_id'),
                operation_ontology_sources=step.get('operation_ontology_sources'),
                kefc_provenance=facts,
                kefc_step_number=step['step_number'],
                validation_status=step['validation_status'],
            )

            if step.get('tool_id'):
                tool_node = f"tool_{step['tool_id']}"
                if self.G.has_node(tool_node):
                    self.G.add_edge(
                        instance_node, tool_node,
                        relationship='USES',
                        tool_type=step['tool_id'],
                        rule_id=step.get('tool_selection_rule_id'),
                    )

            machine_node = f"machine_{step.get('machine', 'cnc_lathe')}"
            if self.G.has_node(machine_node):
                self.G.add_edge(instance_node, machine_node, relationship='RUNS_ON')

            material_node = f"material_{step.get('material', 'steel_1045')}"
            if self.G.has_node(material_node):
                self.G.add_edge(instance_node, material_node, relationship='REMOVES')

        # SEQUENCE_BEFORE directly between consecutive step-instance nodes —
        # every consecutive pair, since instance nodes (unlike the old
        # shared type nodes) never collide between same-type steps.
        ordered_steps = sorted(instance_node_by_step.keys())
        for step_from, step_to in zip(ordered_steps, ordered_steps[1:]):
            self.G.add_edge(
                instance_node_by_step[step_from], instance_node_by_step[step_to],
                relationship='SEQUENCE_BEFORE',
                step_from=step_from, step_to=step_to,
            )

    def apply_expert_resolutions(self, expert_requests: Optional[List] = None):
        """Mark REQUIRES edges approvedByExpert where a matching request was resolved.

        REQUIRES edges now go feature -> operation-INSTANCE node (see
        populate_decisions_from_kefc), not feature -> operation-type node, so
        this searches the feature's REQUIRES-connected instance nodes for one
        whose operation_type matches the request — comparing both the
        request's own value and its OWL_OPERATION_TO_LEGACY_ID-mapped form,
        since ExpertValidationRequest.operation is recorded as the ontology
        individual's name (e.g. "RoughTurningOp") while instance nodes'
        operation_type is the legacy id (e.g. "rough_turning")."""
        for req in (expert_requests or []):
            if req.status != 'expert_approved':
                continue
            feature_node = f"feature_{req.feature_id}"
            if not req.operation:
                continue
            candidates = {req.operation, OWL_OPERATION_TO_LEGACY_ID.get(req.operation, req.operation)}
            for successor in list(self.G.successors(feature_node)) if self.G.has_node(feature_node) else []:
                edge = self.G[feature_node][successor]
                if edge.get('relationship') != 'REQUIRES':
                    continue
                if self.G.nodes[successor].get('operation_type') not in candidates:
                    continue
                facts = set(edge.get('kefc_provenance', []))
                facts.add('approvedByExpert')
                edge['kefc_provenance'] = sorted(facts)
                edge['expert_request_id'] = req.request_id
                edge['expert_resolved_at'] = req.resolved_at

    def get_operations_for_feature(self, feature_id: int) -> List[Dict]:
        """
        Query KG for operations required for a feature.

        REQUIRES targets are now operation-INSTANCE nodes (one per planned
        step), not the shared operation-type vocabulary node — each result
        below is resolved back to its type node for the descriptive fields
        (name/description/parameters/g_codes/cycle_codes), plus the
        instance's own step_number/tool_id/validation_status for per-step
        precision that a shared type node couldn't have provided.

        Args:
            feature_id: Feature identifier

        Returns:
            List of operation dictionaries
        """
        feature_node = f"feature_{feature_id}"

        if not self.G.has_node(feature_node):
            return []

        operations = []

        # Find operations connected via REQUIRES edges
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
                    'parameters': op_data.get('parameters'),
                    'g_codes': op_data.get('g_codes'),
                    'cycle_codes': op_data.get('cycle_codes'),
                    'instance_id': neighbor,
                    'step_number': instance_data.get('step_number'),
                    'tool_id': instance_data.get('tool_id'),
                    'validation_status': instance_data.get('validation_status'),
                })

        return operations

    def get_tool_for_operation(self, operation_id: str) -> Dict:
        """
        Query KG for tool used in an operation.

        Accepts either a type-level operation id (e.g. "rough_turning" —
        vocabulary node `op_rough_turning`) or a specific step's instance id
        (e.g. "opstep_3"). For a type-level id, since one operation type can
        now back multiple planned steps that could in principle use
        different tools, this returns the first matching instance's tool —
        callers that need a specific step's tool should pass its instance_id
        (see get_operations_for_feature's returned 'instance_id') instead.

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

        # Find tools connected via USES edges
        for neighbor in self.G.successors(op_node):
            edge_data = self.G[op_node][neighbor]

            if edge_data.get('relationship') == 'USES':
                tool_data = self.G.nodes[neighbor]
                return {
                    'tool_id': tool_data['id'],
                    'tool_name': tool_data['name'],
                    'type': tool_data['type'],
                    'material': tool_data['material'],
                    'geometry': tool_data['geometry']
                }

        return {}
    
    def get_machining_sequence(self) -> List[Dict]:
        """
        Get the complete machining sequence from KG.

        `operation_from`/`operation_to` are now operation-INSTANCE node ids
        (e.g. "opstep_3"), one per planned step, rather than shared
        operation-type ids — every consecutive step-to-step transition is
        represented (previously, transitions between two steps of the same
        operation type were dropped entirely; see populate_decisions_from_kefc).
        `operation_type_from`/`operation_type_to` are added for readability.

        Returns:
            List of operation steps in order
        """
        sequence = []

        # Find all SEQUENCE_BEFORE edges
        for u, v, data in self.G.edges(data=True):
            if data.get('relationship') == 'SEQUENCE_BEFORE':
                sequence.append({
                    'step_from': data['step_from'],
                    'step_to': data['step_to'],
                    'operation_from': u,
                    'operation_to': v,
                    'operation_type_from': self.G.nodes[u].get('operation_type'),
                    'operation_type_to': self.G.nodes[v].get('operation_type'),
                })
        
        # Sort by step number
        sequence.sort(key=lambda x: x['step_from'])
        
        return sequence
    
    # Note: an earlier version of this class had `add_kefc_provenance()`, a
    # bolt-on pass that added provenance to edges *build_kg()* (the
    # ontology.py-driven path) had already created. That meant the unified
    # graph's actual structure (which operations/tools/sequence) was still
    # ontology.py-authoritative, with SKL/KEFC provenance merely annotated on
    # top — not what "the unified graph must be SKL-authoritative" requires.
    # It's replaced by `build_kg_from_skl()` + `populate_decisions_from_kefc()`
    # above, which build the graph's actual REQUIRES/USES/etc. edges from the
    # KEFC plan directly, with provenance attached at creation, not after.

    def get_graph_stats(self) -> Dict:
        """
        Get statistics about the KG.
        
        Returns:
            Dict with node and edge counts by type
        """
        stats = {
            'total_nodes': self.G.number_of_nodes(),
            'total_edges': self.G.number_of_edges(),
            'node_types': defaultdict(int),
            'edge_types': defaultdict(int)
        }
        
        # Count node types
        for node, data in self.G.nodes(data=True):
            node_type = data.get('node_type', 'unknown')
            stats['node_types'][node_type] += 1
        
        # Count edge types
        for u, v, data in self.G.edges(data=True):
            edge_type = data.get('relationship', 'unknown')
            stats['edge_types'][edge_type] += 1
        
        return stats
    
    def visualize_graph(self, filepath: Optional[str] = None):
        """
        Visualize the KG using matplotlib.
        
        Args:
            filepath: Optional path to save the visualization
        """
        try:
            import matplotlib.pyplot as plt
            
            # Create spring layout
            pos = nx.spring_layout(self.G, k=0.5, iterations=50)
            
            # Get node colors by type
            node_colors = []
            color_map = {
                'feature': '#FF6B6B',
                'operation': '#4ECDC4',
                'operation_instance': '#1A9C90',
                'tool': '#45B7D1',
                'machine': '#96CEB4',
                'material': '#FFEAA7',
                'parameter': '#DDA0DD'
            }
            
            for node in self.G.nodes():
                node_type = self.G.nodes[node].get('node_type', 'unknown')
                node_colors.append(color_map.get(node_type, '#95A5A6'))
            
            # Draw graph
            plt.figure(figsize=(20, 16))
            nx.draw(
                self.G,
                pos,
                node_color=node_colors,
                node_size=300,
                with_labels=True,
                font_size=8,
                font_weight='bold',
                edge_color='gray',
                arrows=True,
                arrowsize=20
            )
            
            # Add title
            plt.title("Manufacturing Knowledge Graph", fontsize=16, fontweight='bold')
            plt.tight_layout()
            
            if filepath:
                plt.savefig(filepath, dpi=300, bbox_inches='tight')
                print(f"Graph visualization saved to: {filepath}")
            else:
                plt.show()
            
        except ImportError:
            print("Matplotlib not available. Install with: pip install matplotlib")
    
    def export_to_json(self, filepath: str) -> str:
        """
        Export KG to JSON format.
        
        Args:
            filepath: Path to save JSON file
            
        Returns:
            JSON string
        """
        import json
        
        # Convert graph to JSON-serializable format
        graph_data = {
            'nodes': [],
            'edges': []
        }
        
        # Export nodes
        for node, data in self.G.nodes(data=True):
            graph_data['nodes'].append({
                'id': node,
                **data
            })
        
        # Export edges
        for u, v, data in self.G.edges(data=True):
            graph_data['edges'].append({
                'source': u,
                'target': v,
                **data
            })
        
        json_str = json.dumps(graph_data, indent=2, default=str)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(json_str)
        
        return json_str
    
    def export_to_rdf(self, filepath: str, schema_path: Optional[str] = None) -> 'ManufacturingTriplestore':
        """
        Export NetworkX KG to RDF triplestore.
        
        Converts the NetworkX graph to an RDF triplestore using rdflib,
        enabling SPARQL query execution and semantic web interoperability.
        
        Args:
            filepath: Path to save the serialized RDF graph (Turtle format)
            schema_path: Optional path to OntoBREP schema (.ttl) to load first
            
        Returns:
            ManufacturingTriplestore instance with the exported data
        """
        try:
            from rdf_triplestore import ManufacturingTriplestore
        except ImportError:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from rdf_triplestore import ManufacturingTriplestore
        
        # Create triplestore instance
        ts = ManufacturingTriplestore()
        
        # Load schema if provided
        if schema_path and os.path.exists(schema_path):
            ts.load_schema(schema_path)
        
        # Import NetworkX graph into triplestore
        ts.import_from_networkx(self.G)
        
        # Serialize to file
        ts.serialize(filepath, format="turtle")
        
        print(f"RDF triplestore exported to: {filepath}")
        print(f"Total triples: {ts.get_triple_count()}")
        print(f"Node counts: {ts.get_node_counts()}")
        
        return ts

