"""
RDF Triplestore Module
======================
RDF/SPARQL-based knowledge graph using rdflib for manufacturing data.
Provides parallel backend to NetworkX with SPARQL query capabilities.

Architecture:
- In-memory RDF graph using rdflib
- OntoBREP-aligned schema (manufacturing.ttl)
- NetworkX import/export for parallel backend design
- SPARQL query execution with validation

Classes:
- ManufacturingTriplestore: RDF triplestore with SPARQL query interface
"""

import rdflib
from rdflib import Graph, Namespace, RDF, RDFS, OWL, XSD, Literal, URIRef
from rdflib.namespace import NamespaceManager
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

# Define namespaces
MFG = Namespace("http://onto.brep.org/manufacturing#")
BREP = Namespace("http://onto.brep.org/boundary#")

# feature_parser.py's dimension regex captures the raw CAD symbol used in the
# source drawings/STEP annotations — never the English word. Used by
# add_feature() to also assert a semantic mfg:dimensionType alongside the
# literal mfg:dimensionKey symbol.
DIMENSION_SYMBOL_TO_TYPE = {
    "Ø": "diameter",
    "L": "length",
    "R": "radius",
    "W": "width",
}


class ManufacturingTriplestore:
    """
    RDF triplestore for manufacturing knowledge graph.
    
    Provides:
    - RDF graph construction from ontology and feature data
    - SPARQL query execution
    - NetworkX graph import/export
    - Triple count validation
    - Schema-aware query patterns
    
    Usage:
        ts = ManufacturingTriplestore()
        ts.load_schema("manufacturing.ttl")
        ts.add_feature(feature_data)
        ts.add_operation(op_data)
        results = ts.execute_sparql(query_string)
    """
    
    def __init__(self):
        """Initialize an empty RDF graph with namespace management."""
        self.g = Graph()
        
        # Set up namespace manager
        self.namespace_manager = NamespaceManager(self.g)
        self.namespace_manager.bind("rdf", RDF)
        self.namespace_manager.bind("rdfs", RDFS)
        self.namespace_manager.bind("owl", OWL)
        self.namespace_manager.bind("xsd", XSD)
        self.namespace_manager.bind("mfg", MFG)
        self.namespace_manager.bind("brep", BREP)
        
        # Track node counts
        self._node_counters = {"feature": 0, "operation": 0, "operation_instance": 0,
                               "tool": 0, "machine": 0, "material": 0, "parameter": 0}
        
        logger.info("ManufacturingTriplestore initialized with empty RDF graph")
    
    def load_schema(self, schema_path: str) -> int:
        """
        Load OntoBREP schema from Turtle file.
        
        Args:
            schema_path: Path to .ttl schema file
            
        Returns:
            Number of triples added from schema
        """
        schema_graph = Graph()
        schema_graph.parse(schema_path, format="turtle")
        
        initial_count = len(self.g)
        self.g += schema_graph
        added_count = len(self.g) - initial_count
        
        logger.info(f"Loaded schema from {schema_path}: {added_count} triples added")
        return added_count
    
    def _create_uri(self, node_id: str, node_type: str) -> URIRef:
        """
        Create URI reference for a node based on type.
        
        Args:
            node_id: Node identifier
            node_type: Node type (feature, operation, tool, etc.)
            
        Returns:
            URIRef for the node
        """
        type_to_class = {
            "feature": MFG.Feature,
            "operation": MFG.Operation,
            "operation_instance": MFG.Operation,
            "tool": MFG.Tool,
            "machine": MFG.Machine,
            "material": MFG.Material,
            "parameter": MFG.Parameter
        }
        
        class_uri = type_to_class.get(node_type, MFG.Entity)
        return URIRef(f"{MFG}{node_id.replace(':', '_')}")
    
    def add_feature(self, feature: Dict) -> URIRef:
        """
        Add a feature node to the RDF graph.
        
        Args:
            feature: Feature dictionary with id, type, dimensions, etc.
            
        Returns:
            URIRef of the created feature node
        """
        feature_id = feature['id']
        feature_type = feature['type']
        node_id = f"feature_{feature_id}"
        
        feature_uri = self._create_uri(node_id, "feature")
        
        # Add type
        self.g.add((feature_uri, RDF.type, MFG.Feature))
        
        # Add attributes
        self.g.add((feature_uri, MFG.id, Literal(str(feature_id))))
        self.g.add((feature_uri, MFG.nodeType, Literal("feature")))
        self.g.add((feature_uri, MFG.name, Literal(f"Feature {feature_id} ({feature_type})")))
        # mfg:name embeds the type as parenthetical text only — that's not a
        # queryable predicate, so a distinct mfg:featureType is asserted too
        # (see sparql_examples.py example #5).
        self.g.add((feature_uri, MFG.featureType, Literal(feature_type)))

        if 'description' in feature:
            self.g.add((feature_uri, MFG.description, Literal(feature['description'])))

        # Add dimensions as parameters. dim_key is the raw CAD symbol
        # (Ø/L/R/W, from feature_parser.py's dimension regex) — dimensionType
        # additionally classifies it semantically (diameter/length/radius/
        # width) so a query can ask "find the diameter" without already
        # knowing the symbol convention (see sparql_examples.py examples #7, #10).
        dimensions = feature.get('dimensions', {})
        for dim_key, dim_value in dimensions.items():
            param_data = {"key": dim_key, "value": str(dim_value)}
            dim_type = DIMENSION_SYMBOL_TO_TYPE.get(dim_key)
            if dim_type:
                param_data["dimension_type"] = dim_type
            dim_uri = self._add_parameter(
                f"dim_{feature_id}_{dim_key}",
                "dimension",
                param_data
            )
            self.g.add((feature_uri, MFG.hasDimension, dim_uri))
        
        # Add location as parameter
        location = feature.get('absolute_location', {})
        if location:
            loc_uri = self._add_parameter(
                f"loc_{feature_id}",
                "location",
                {"coordinates": json.dumps(location)}
            )
            self.g.add((feature_uri, MFG.locatedAt, loc_uri))
        
        self._node_counters["feature"] += 1
        logger.debug(f"Added feature node: {node_id}")
        
        return feature_uri
    
    def add_operation(self, op_id: str, op_data: Dict) -> URIRef:
        """
        Add an operation node to the RDF graph.
        
        Args:
            op_id: Operation identifier
            op_data: Operation dictionary with name, parameters, etc.
            
        Returns:
            URIRef of the created operation node
        """
        node_id = f"op_{op_id}"
        op_uri = self._create_uri(node_id, "operation")
        
        # Add type
        self.g.add((op_uri, RDF.type, MFG.Operation))
        
        # Add attributes
        self.g.add((op_uri, MFG.id, Literal(op_id)))
        self.g.add((op_uri, MFG.nodeType, Literal("operation")))
        self.g.add((op_uri, MFG.name, Literal(op_data.get('name', op_id))))
        
        if 'description' in op_data:
            self.g.add((op_uri, MFG.description, Literal(op_data['description'])))
        
        # Add G-codes as parameters, linked back to the operation (previously
        # built but never linked — an unreachable/orphan node; see
        # sparql_examples.py example #15).
        g_codes = op_data.get('g_codes', [])
        if g_codes:
            params_uri = self._add_parameter(
                f"params_{op_id}",
                "g_codes",
                {"value": json.dumps(g_codes)}
            )
            self.g.add((op_uri, MFG.hasGCodes, params_uri))

        self._node_counters["operation"] += 1
        logger.debug(f"Added operation node: {node_id}")

        return op_uri

    def add_operation_instance(self, instance_node_id: str, instance_data: Dict) -> URIRef:
        """
        Add a per-step operation-INSTANCE node to the RDF graph — distinct
        from `add_operation`'s per-TYPE vocabulary node (e.g. "RoughTurningOp"
        in general) — representing one specific planned step (e.g. "rough
        turning, step 3, on feature 5"). Without this, `import_from_networkx`
        would silently drop instance nodes entirely (no branch matched their
        `node_type`), leaving their URIs referenced by REQUIRES/USES/etc.
        edges but never actually typed/described as RDF individuals.

        Args:
            instance_node_id: the NetworkX node id, e.g. "opstep_3"
            instance_data: dict with operation_type (the vocabulary node's
                legacy id this instantiates), step_number, feature_id,
                tool_id, validation_status, name, description (the latter
                two copied from the type node — see kg_builder.py's
                populate_decisions_from_kefc — so queries reaching this node
                via mfg:requires can read mfg:name directly, as they could
                when mfg:requires pointed at the type node)

        Returns:
            URIRef of the created operation-instance node
        """
        instance_uri = self._create_uri(instance_node_id, "operation")

        self.g.add((instance_uri, RDF.type, MFG.Operation))
        self.g.add((instance_uri, MFG.nodeType, Literal("operation_instance")))
        self.g.add((instance_uri, MFG.id, Literal(instance_node_id)))
        self.g.add((instance_uri, MFG.stepNumber, Literal(instance_data.get('step_number', 0))))
        self.g.add((instance_uri, MFG.name, Literal(instance_data.get('name') or instance_node_id)))
        if instance_data.get('description'):
            self.g.add((instance_uri, MFG.description, Literal(instance_data['description'])))

        operation_type = instance_data.get('operation_type')
        if operation_type:
            type_uri = self._create_uri(f"op_{operation_type}", "operation")
            self.g.add((instance_uri, MFG.instanceOfOperationType, type_uri))

        if instance_data.get('validation_status'):
            self.g.add((instance_uri, MFG.validationStatus, Literal(instance_data['validation_status'])))

        for param_name, record in sorted((instance_data.get('parameters') or {}).items()):
            if isinstance(record, dict):
                self.add_parameter_record(instance_uri, instance_data.get('step_number', 0), param_name, record)

        self._node_counters["operation_instance"] += 1
        logger.debug(f"Added operation-instance node: {instance_node_id}")

        return instance_uri
    
    def add_tool(self, tool_id: str, tool_data: Dict) -> URIRef:
        """
        Add a tool node to the RDF graph.
        
        Args:
            tool_id: Tool identifier
            tool_data: Tool dictionary with name, type, geometry, etc.
            
        Returns:
            URIRef of the created tool node
        """
        node_id = f"tool_{tool_id}"
        tool_uri = self._create_uri(node_id, "tool")
        
        # Add type
        self.g.add((tool_uri, RDF.type, MFG.Tool))
        
        # Add attributes
        self.g.add((tool_uri, MFG.id, Literal(tool_id)))
        self.g.add((tool_uri, MFG.nodeType, Literal("tool")))
        self.g.add((tool_uri, MFG.name, Literal(tool_data.get('name', tool_id))))
        
        if 'type' in tool_data:
            self.g.add((tool_uri, MFG.toolType, Literal(tool_data['type'])))
        
        if 'material' in tool_data:
            self.g.add((tool_uri, MFG.materialType, Literal(tool_data['material'])))
        
        if 'geometry' in tool_data:
            self.g.add((tool_uri, MFG.geometry, Literal(tool_data['geometry'])))
        
        self._node_counters["tool"] += 1
        logger.debug(f"Added tool node: {node_id}")
        
        return tool_uri
    
    def add_machine(self, machine_id: str, machine_data: Dict) -> URIRef:
        """
        Add a machine node to the RDF graph.
        
        Args:
            machine_id: Machine identifier
            machine_data: Machine dictionary with name, capabilities, etc.
            
        Returns:
            URIRef of the created machine node
        """
        node_id = f"machine_{machine_id}"
        machine_uri = self._create_uri(node_id, "machine")
        
        # Add type
        self.g.add((machine_uri, RDF.type, MFG.Machine))
        
        # Add attributes
        self.g.add((machine_uri, MFG.id, Literal(machine_id)))
        self.g.add((machine_uri, MFG.nodeType, Literal("machine")))
        self.g.add((machine_uri, MFG.name, Literal(machine_data.get('name', machine_id))))
        
        # Add capabilities
        capabilities = machine_data.get('capabilities', [])
        for cap in capabilities:
            self.g.add((machine_uri, MFG.capability, Literal(cap)))
        
        self._node_counters["machine"] += 1
        logger.debug(f"Added machine node: {node_id}")
        
        return machine_uri
    
    def add_material(self, material_id: str, material_data: Dict) -> URIRef:
        """
        Add a material node to the RDF graph.
        
        Args:
            material_id: Material identifier
            material_data: Material dictionary with name, properties, etc.
            
        Returns:
            URIRef of the created material node
        """
        node_id = f"material_{material_id}"
        material_uri = self._create_uri(node_id, "material")
        
        # Add type
        self.g.add((material_uri, RDF.type, MFG.Material))
        
        # Add attributes
        self.g.add((material_uri, MFG.id, Literal(material_id)))
        self.g.add((material_uri, MFG.nodeType, Literal("material")))
        self.g.add((material_uri, MFG.name, Literal(material_data.get('name', material_id))))
        
        if 'type' in material_data:
            self.g.add((material_uri, MFG.materialType, Literal(material_data['type'])))
        
        self._node_counters["material"] += 1
        logger.debug(f"Added material node: {node_id}")
        
        return material_uri
    
    def _add_parameter(self, param_id: str, param_type: str, param_data: Dict) -> URIRef:
        """
        Add a parameter node to the RDF graph.
        
        Args:
            param_id: Parameter identifier
            param_type: Parameter type (dimension, location, etc.)
            param_data: Parameter dictionary with key, value, etc.
            
        Returns:
            URIRef of the created parameter node
        """
        param_uri = self._create_uri(param_id, "parameter")
        
        # Add type
        self.g.add((param_uri, RDF.type, MFG.Parameter))
        
        # Add attributes
        self.g.add((param_uri, MFG.id, Literal(param_id)))
        self.g.add((param_uri, MFG.nodeType, Literal("parameter")))
        self.g.add((param_uri, MFG.parameterType, Literal(param_type)))
        
        if 'key' in param_data:
            self.g.add((param_uri, MFG.dimensionKey, Literal(param_data['key'])))

        if 'dimension_type' in param_data:
            self.g.add((param_uri, MFG.dimensionType, Literal(param_data['dimension_type'])))

        if 'value' in param_data:
            self.g.add((param_uri, MFG.value, Literal(param_data['value'])))
        
        if 'coordinates' in param_data:
            self.g.add((param_uri, MFG.coordinates, Literal(param_data['coordinates'])))
        
        self._node_counters["parameter"] += 1
        logger.debug(f"Added parameter node: {param_id}")
        
        return param_uri
    
    def add_parameter_record(self, step_uri: URIRef, step_number: int, param_name: str,
                             record: Dict) -> URIRef:
        """
        Publish one KEFC parameter record of a plan step as an RDF resource
        mfg:param_<step>_<name>, so that its value, unit, rule identifier,
        ontology sources and input facts can be resolved by SPARQL:

            <step> mfg:hasParameterRecord <param> .
            <param> a mfg:ParameterRecord ; mfg:stepNumber n ;
                mfg:parameterName "spindle_speed" ; mfg:value 480.0 (typed) ;
                mfg:unit "RPM" ; mfg:ruleId "..." ; mfg:source "swrl_rule" ;
                mfg:ontologySource <iri> (one triple per IRI) ;
                mfg:inputFeatureId ; mfg:inputFeatureType ; mfg:inputMaterial ;
                mfg:inputMappingConfidence .

        mfg:ParameterRecord is deliberately distinct from mfg:Parameter
        (feature dimension/location nodes), so existing queries and node
        counts over mfg:Parameter are unaffected.
        """
        uri = URIRef(f"{MFG}param_{step_number}_{param_name}")
        self.g.add((step_uri, MFG.hasParameterRecord, uri))
        self.g.add((uri, RDF.type, MFG.ParameterRecord))
        self.g.add((uri, MFG.stepNumber, Literal(step_number)))
        self.g.add((uri, MFG.parameterName, Literal(param_name)))
        value = record.get('value')
        if isinstance(value, bool):
            self.g.add((uri, MFG.value, Literal(value, datatype=XSD.boolean)))
        elif isinstance(value, (int, float)):
            self.g.add((uri, MFG.value, Literal(float(value), datatype=XSD.double)))
        elif value is not None:
            self.g.add((uri, MFG.value, Literal(str(value))))
        if record.get('unit') is not None:
            self.g.add((uri, MFG.unit, Literal(str(record['unit']))))
        if record.get('rule_id'):
            self.g.add((uri, MFG.ruleId, Literal(str(record['rule_id']))))
        if record.get('source'):
            self.g.add((uri, MFG.source, Literal(str(record['source']))))
        for iri in record.get('ontology_sources') or []:
            self.g.add((uri, MFG.ontologySource, URIRef(str(iri))))
        facts = record.get('input_facts') or {}
        if facts.get('feature_id') is not None:
            self.g.add((uri, MFG.inputFeatureId, Literal(str(facts['feature_id']))))
        if facts.get('feature_type') is not None:
            self.g.add((uri, MFG.inputFeatureType, Literal(str(facts['feature_type']))))
        if facts.get('material') is not None:
            self.g.add((uri, MFG.inputMaterial, Literal(str(facts['material']))))
        if facts.get('mapping_confidence') is not None:
            self.g.add((uri, MFG.inputMappingConfidence,
                        Literal(float(facts['mapping_confidence']), datatype=XSD.double)))
        return uri

    def add_relationship(self, subject_uri: URIRef, predicate: URIRef, 
                        object_uri: URIRef, **kwargs) -> None:
        """
        Add a relationship (triple) to the RDF graph.
        
        Args:
            subject_uri: Subject URI
            predicate: Predicate URI (relationship type)
            object_uri: Object URI
            **kwargs: Additional attributes for the relationship
        """
        self.g.add((subject_uri, predicate, object_uri))

        # Add reification if additional attributes provided
        if kwargs:
            for key, value in kwargs.items():
                if value in (None, "", []):
                    continue
                attr_uri = URIRef(f"{MFG}{key}")
                # List-valued attributes (e.g. rule_ids, ontology_sources,
                # kefc_provenance) are joined into one "|"-delimited literal
                # rather than str()'d as a Python repr — keeps them usable in
                # a SPARQL CONTAINS() filter instead of opaque ["a", "b"] text.
                if isinstance(value, (list, tuple, set)):
                    value = "|".join(str(v) for v in value)
                # Create blank node for reified triple
                bnode = rdflib.BNode()
                self.g.add((bnode, RDF.type, RDF.Statement))
                self.g.add((bnode, RDF.subject, subject_uri))
                self.g.add((bnode, RDF.predicate, predicate))
                self.g.add((bnode, RDF.object, object_uri))
                self.g.add((bnode, attr_uri, Literal(str(value))))
        
        logger.debug(f"Added relationship: {subject_uri} -> {predicate} -> {object_uri}")
    
    def add_requires(self, feature_uri: URIRef, op_uri: URIRef, confidence: float = 1.0,
                      **provenance) -> None:
        """Add REQUIRES relationship: Feature requires Operation.

        `**provenance` carries KEFC's traceability facts through to the RDF
        export (rule_ids, ontology_sources, kefc_provenance, validation_status,
        kefc_step_number) — without this, the unified graph's RDF/Turtle
        export would drop the very traceability that's the point of the
        SKL/KEFC retrofit (see AGENTS.md, .codex/development_plan.md Phase 8)."""
        self.add_relationship(feature_uri, MFG.requires, op_uri, confidence=confidence, **provenance)

    def add_uses(self, op_uri: URIRef, tool_uri: URIRef, tool_type: str = "",
                 **provenance) -> None:
        """Add USES relationship: Operation uses Tool."""
        self.add_relationship(op_uri, MFG.uses, tool_uri, toolType=tool_type, **provenance)
    
    def add_runs_on(self, op_uri: URIRef, machine_uri: URIRef) -> None:
        """Add RUNS_ON relationship: Operation runs on Machine."""
        self.add_relationship(op_uri, MFG.runsOn, machine_uri)
    
    def add_removes(self, op_uri: URIRef, material_uri: URIRef) -> None:
        """Add REMOVES relationship: Operation removes Material."""
        self.add_relationship(op_uri, MFG.removes, material_uri)
    
    def add_sequence_before(self, op_from_uri: URIRef, op_to_uri: URIRef, 
                           step_from: int, step_to: int) -> None:
        """Add SEQUENCE_BEFORE relationship: Operation before another."""
        self.add_relationship(op_from_uri, MFG.sequenceBefore, op_to_uri,
                            stepFrom=step_from, stepTo=step_to)
    
    def execute_sparql(self, query: str, init_ns: Optional[Dict] = None) -> List[Dict]:
        """
        Execute a SPARQL query on the RDF graph.
        
        Args:
            query: SPARQL query string
            init_ns: Optional namespace dictionary for query resolution
            
        Returns:
            List of dictionaries with query results
        """
        try:
            # Set up namespaces for query
            namespaces = {
                "rdf": RDF,
                "rdfs": RDFS,
                "owl": OWL,
                "xsd": XSD,
                "mfg": MFG,
                "brep": BREP
            }
            
            if init_ns:
                namespaces.update(init_ns)
            
            # Execute query
            results = self.g.query(query, initNs=namespaces)
            
            # Convert results to list of dictionaries
            result_list = []
            for row in results:
                row_dict = {}
                for var in results.vars:
                    var_name = str(var) if var else "unknown"
                    # getattr() requires an exact `str`, not a subclass
                    # instance — rdflib.term.Variable IS a str subclass, but
                    # passing it directly to getattr() raises AttributeError
                    # regardless of whether the row actually has that
                    # binding (a CPython getattr() quirk, not a rdflib bug).
                    value = getattr(row, var_name, None)
                    if value is not None:
                        if isinstance(value, URIRef):
                            row_dict[var_name] = str(value)
                        elif isinstance(value, Literal):
                            row_dict[var_name] = str(value)
                        else:
                            row_dict[var_name] = str(value)
                result_list.append(row_dict)
            
            logger.info(f"SPARQL query executed: {len(result_list)} results returned")
            return result_list
            
        except Exception as e:
            logger.error(f"SPARQL query execution failed: {e}")
            raise
    
    def get_triple_count(self) -> int:
        """Get total number of triples in the graph."""
        return len(self.g)
    
    def get_node_counts(self) -> Dict[str, int]:
        """Get counts of nodes by type."""
        return dict(self._node_counters)
    
    def serialize(self, filepath: str, format: str = "turtle") -> None:
        """
        Serialize the RDF graph to a file.
        
        Args:
            filepath: Output file path
            format: Serialization format (turtle, xml, n3, json-ld)
        """
        self.g.serialize(destination=filepath, format=format)
        logger.info(f"RDF graph serialized to {filepath} ({format} format, {len(self.g)} triples)")
    
    def export_to_networkx(self) -> 'nx.DiGraph':
        """
        Export RDF graph to NetworkX DiGraph.
        
        Returns:
            NetworkX DiGraph with nodes and edges from RDF triples
        """
        import networkx as nx
        
        G = nx.DiGraph()
        G.name = "Manufacturing_Knowledge_Graph_from_RDF"
        
        # Extract nodes and their types
        for s, p, o in self.g:
            if p == RDF.type:
                # This is a type declaration
                node_id = str(s).split('#')[-1]
                node_type = str(o).split('#')[-1]
                
                # Map type names to node_type values
                type_map = {
                    "Feature": "feature",
                    "Operation": "operation",
                    "Tool": "tool",
                    "Machine": "machine",
                    "Material": "material",
                    "Parameter": "parameter"
                }
                
                G.add_node(node_id, node_type=type_map.get(node_type, node_type.lower()))
            else:
                # This is a relationship or attribute
                subject_id = str(s).split('#')[-1]
                object_id = str(o).split('#')[-1]
                
                # Ensure nodes exist
                if not G.has_node(subject_id):
                    G.add_node(subject_id, node_type="unknown")
                if not G.has_node(object_id):
                    G.add_node(object_id, node_type="unknown")
                
                # Determine relationship type
                predicate_str = str(p)
                if "requires" in predicate_str:
                    rel_type = "REQUIRES"
                elif "uses" in predicate_str:
                    rel_type = "USES"
                elif "runsOn" in predicate_str:
                    rel_type = "RUNS_ON"
                elif "removes" in predicate_str:
                    rel_type = "REMOVES"
                elif "sequenceBefore" in predicate_str:
                    rel_type = "SEQUENCE_BEFORE"
                elif "hasDimension" in predicate_str:
                    rel_type = "HAS_DIMENSION"
                elif "locatedAt" in predicate_str:
                    rel_type = "LOCATED_AT"
                else:
                    rel_type = "UNKNOWN"
                
                G.add_edge(subject_id, object_id, relationship=rel_type)
        
        logger.info(f"Exported RDF graph to NetworkX: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        
        return G
    
    def import_from_networkx(self, G: 'nx.DiGraph') -> None:
        """
        Import NetworkX graph into RDF triplestore.
        
        Args:
            G: NetworkX DiGraph with manufacturing knowledge
        """
        # Add nodes based on type
        for node, data in G.nodes(data=True):
            node_type = data.get('node_type', 'unknown')
            
            if node_type == 'feature':
                feature_data = {
                    'id': data.get('id', node.replace('feature_', '')),
                    'type': data.get('type', ''),
                    'description': data.get('description', ''),
                    'dimensions': {},
                    'absolute_location': {}
                }
                # Extract dimensions and location from node data
                if 'dimensions' in data:
                    feature_data['dimensions'] = data['dimensions']
                if 'absolute_location' in data:
                    feature_data['absolute_location'] = data['absolute_location']
                self.add_feature(feature_data)
            
            elif node_type == 'operation':
                op_data = {
                    'name': data.get('name', node.replace('op_', '')),
                    'description': data.get('description', ''),
                    'parameters': data.get('parameters', {}),
                    'g_codes': data.get('g_codes', []),
                    'cycle_codes': data.get('cycle_codes', [])
                }
                op_id = data.get('id', node.replace('op_', ''))
                self.add_operation(op_id, op_data)

            elif node_type == 'operation_instance':
                self.add_operation_instance(node, {
                    'operation_type': data.get('operation_type'),
                    'step_number': data.get('step_number', 0),
                    'feature_id': data.get('feature_id'),
                    'tool_id': data.get('tool_id'),
                    'validation_status': data.get('validation_status'),
                    'name': data.get('name'),
                    'description': data.get('description'),
                    'parameters': data.get('parameters', {}),
                })

            elif node_type == 'tool':
                tool_data = {
                    'name': data.get('name', node.replace('tool_', '')),
                    'type': data.get('type', ''),
                    'material': data.get('material', ''),
                    'geometry': data.get('geometry', ''),
                    'recommended_operations': data.get('recommended_operations', [])
                }
                tool_id = data.get('id', node.replace('tool_', ''))
                self.add_tool(tool_id, tool_data)
            
            elif node_type == 'machine':
                machine_data = {
                    'name': data.get('name', node.replace('machine_', '')),
                    'model': data.get('model', ''),
                    'capabilities': data.get('capabilities', []),
                    'supported_operations': data.get('supported_operations', []),
                    'safety_limits': data.get('safety_limits', {})
                }
                machine_id = data.get('id', node.replace('machine_', ''))
                self.add_machine(machine_id, machine_data)
            
            elif node_type == 'material':
                material_data = {
                    'name': data.get('name', node.replace('material_', '')),
                    'type': data.get('type', ''),
                    'properties': data.get('properties', {}),
                    'cutting_parameters': data.get('cutting_parameters', {}),
                    'machinability_rating': data.get('machinability_rating', 0)
                }
                material_id = data.get('id', node.replace('material_', ''))
                self.add_material(material_id, material_data)
            
            elif node_type == 'parameter':
                param_data = {
                    'key': data.get('key', ''),
                    'value': str(data.get('value', '')),
                    'coordinates': str(data.get('coordinates', ''))
                }
                self._add_parameter(node, data.get('parameter_type', 'dimension'), param_data)
        
        # Add edges as relationships
        for u, v, data in G.edges(data=True):
            rel_type = data.get('relationship', '')
            
            # Get URIs for subject and object
            subject_uri = self._create_uri(u, G.nodes[u].get('node_type', 'unknown'))
            object_uri = self._create_uri(v, G.nodes[v].get('node_type', 'unknown'))
            
            if rel_type == 'REQUIRES':
                confidence = data.get('confidence', 1.0)
                self.add_requires(
                    subject_uri, object_uri, confidence,
                    ruleIds=data.get('rule_ids'),
                    ontologySources=data.get('ontology_sources'),
                    kefcProvenance=data.get('kefc_provenance'),
                    validationStatus=data.get('validation_status'),
                    kefcStepNumber=data.get('kefc_step_number'),
                    expertRequestId=data.get('expert_request_id'),
                    expertResolvedAt=data.get('expert_resolved_at'),
                )
            elif rel_type == 'USES':
                tool_type = data.get('tool_type', '')
                self.add_uses(subject_uri, object_uri, tool_type, ruleId=data.get('rule_id'))
            elif rel_type == 'RUNS_ON':
                self.add_runs_on(subject_uri, object_uri)
            elif rel_type == 'REMOVES':
                self.add_removes(subject_uri, object_uri)
            elif rel_type == 'SEQUENCE_BEFORE':
                step_from = data.get('step_from', 0)
                step_to = data.get('step_to', 0)
                self.add_sequence_before(subject_uri, object_uri, step_from, step_to)
            elif rel_type == 'HAS_DIMENSION':
                self.add_relationship(subject_uri, MFG.hasDimension, object_uri)
            elif rel_type == 'LOCATED_AT':
                self.add_relationship(subject_uri, MFG.locatedAt, object_uri)
            elif rel_type == 'INSTANCE_OF':
                # Operation-instance node -> its operation-type vocabulary
                # node. add_operation_instance() already asserts this same
                # triple directly from the node's own data; this is a
                # harmless duplicate for graphs built/edited via edges only.
                self.add_relationship(subject_uri, MFG.instanceOfOperationType, object_uri)
        
        logger.info(f"Imported NetworkX graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        logger.info(f"RDF triplestore now has {self.get_triple_count()} triples")
