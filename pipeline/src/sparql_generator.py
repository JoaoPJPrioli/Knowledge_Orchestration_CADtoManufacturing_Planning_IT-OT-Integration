"""
SPARQL Generator Module
=======================
LLM-powered SPARQL generation from natural language queries.
Uses Google Gemini API with schema-aware prompts and few-shot learning.

Architecture:
- System prompt engineering with OntoBREP schema context
- Few-shot learning with example NL→SPARQL pairs
- SPARQL syntax validation before execution
- Fallback to deterministic queries on LLM failure

Classes:
- SparqlGenerator: LLM-powered SPARQL generation with Gemini API
"""

import os
import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class SparqlGenerator:
    """
    LLM-powered SPARQL query generator.
    
    Converts natural language queries to SPARQL using Google Gemini API
    with schema-aware prompts and few-shot learning examples.
    
    Features:
    - Schema-aware system prompts
    - Few-shot learning with example queries
    - SPARQL syntax validation
    - Error recovery and retry logic
    - Query caching for performance
    
    Usage:
        gen = SparqlGenerator(api_key="your_key", model="gemini-2.0-flash")
        sparql = gen.generate("What operations are required for feature 1001?")
        results = triplestore.execute_sparql(sparql)
    """
    
    # System prompt template with schema context
    SYSTEM_PROMPT_TEMPLATE = """You are an expert SPARQL query generator for a manufacturing knowledge graph based on the OntoBREP ontology.

Your task is to convert natural language questions about manufacturing processes into valid SPARQL queries.

## Ontology Schema
The knowledge graph uses the following RDF schema:

### Classes (mfg namespace: http://onto.brep.org/manufacturing#)
- mfg:Feature - Geometric features (cylinder, groove, slot, chamfer)
- mfg:Operation - Machining operations (turning, facing, grooving, threading, drilling)
- mfg:Tool - Cutting tools (turning tool, drill bit, groove tool)
- mfg:Machine - Manufacturing machines (CNC lathe)
- mfg:Material - Workpiece materials (steel, aluminum, titanium)
- mfg:Parameter - Machining parameters (dimensions, locations, speeds, feeds)

### Object Properties (relationships)
- mfg:requires - Feature requires Operation
- mfg:uses - Operation uses Tool
- mfg:runsOn - Operation runs on Machine
- mfg:removes - Operation removes Material
- mfg:sequenceBefore - Operation before another in sequence
- mfg:hasDimension - Feature has Dimension parameter
- mfg:locatedAt - Feature located at Position parameter

### Data Properties (attributes)
- mfg:id - Unique identifier
- mfg:name - Human-readable name
- mfg:description - Description text
- mfg:nodeType - Node type (feature, operation, tool, etc.)
- mfg:confidence - Confidence score for relationships
- mfg:stepFrom, mfg:stepTo - Machining sequence steps
- mfg:parameterType - Parameter type (dimension, location)
- mfg:value - Parameter value
- mfg:dimensionKey - Dimension key (diameter, length, depth)
- mfg:coordinates - Spatial coordinates

## Query Patterns
Common query patterns you should know:
1. Find operations for a feature: SELECT operations where feature requires operation
2. Find tools for an operation: SELECT tools where operation uses tool
3. Find machining sequence: SELECT operations ordered by sequenceBefore
4. Find features with specific dimensions: SELECT features with hasDimension parameter
5. Find all tools used in a machining plan: SELECT distinct tools reachable from features

## Important Rules
1. ALWAYS use the mfg: prefix for ontology terms
2. Use SELECT queries for data retrieval
3. Use ASK queries for yes/no questions
4. Use CONSTRUCT queries for graph construction
5. Include proper WHERE clauses with triple patterns
6. Use OPTIONAL for optional properties
7. Use FILTER for value comparisons
8. Return ONLY valid SPARQL - no explanations or markdown
9. Use proper variable names starting with ?
10. Always include PREFIX declarations

## Example Query Structure
```sparql
PREFIX mfg: <http://onto.brep.org/manufacturing#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?operation ?toolName
WHERE {{
    ?feature mfg:id "feature_1001" .
    ?feature mfg:requires ?operation .
    ?operation mfg:uses ?tool .
    ?tool mfg:name ?toolName .
}}
```

Now, convert the following natural language query to SPARQL:"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash",
                 temperature: float = 0.1, max_retries: int = 3):
        """
        Initialize SPARQL generator with Gemini API.
        
        Args:
            api_key: Google Gemini API key (or use GEMINI_API_KEY env var)
            model: Gemini model to use (gemini-2.0-flash, gemini-2.5-pro, gemini-2.5-flash)
            temperature: Generation temperature (0.0-1.0, lower = more deterministic)
            max_retries: Maximum retry attempts on failure
        """
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = model
        self.temperature = temperature
        self.max_retries = max_retries
        
        # Example queries for few-shot learning
        self._examples: List[Dict[str, str]] = []
        
        # Query cache
        self._cache: Dict[str, str] = {}
        
        # Gemini client (lazy initialization)
        self._client = None
        self._model = None
        
        logger.info(f"SparqlGenerator initialized with model={model}, temperature={temperature}")
    
    def _initialize_gemini(self) -> None:
        """Lazy initialization of Gemini API client."""
        if self._model is not None:
            return
        
        try:
            import google.generativeai as genai
            
            if not self.api_key:
                raise ValueError("No API key provided. Set GEMINI_API_KEY environment variable or pass api_key parameter.")
            
            genai.configure(api_key=self.api_key)
            self._client = genai
            self._model = genai.GenerativeModel(self.model_name)
            
            logger.info(f"Gemini API initialized with model {self.model_name}")
            
        except ImportError:
            logger.error("google-generativeai package not installed. Install with: pip install google-generativeai")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Gemini API: {e}")
            raise
    
    def load_examples(self, examples: List[Dict[str, str]]) -> None:
        """
        Load example NL→SPARQL query pairs for few-shot learning.
        
        Args:
            examples: List of dicts with 'question' and 'sparql' keys
        """
        self._examples = examples
        logger.info(f"Loaded {len(examples)} few-shot examples")
    
    def _build_prompt(self, question: str) -> str:
        """
        Build prompt with system context and few-shot examples.
        
        Args:
            question: Natural language question
            
        Returns:
            Complete prompt string for LLM
        """
        prompt = self.SYSTEM_PROMPT_TEMPLATE
        
        # Add few-shot examples if available
        if self._examples:
            prompt += "\n\n## Examples\n\n"
            
            # Use up to 5 most relevant examples
            num_examples = min(5, len(self._examples))
            
            for i, example in enumerate(self._examples[:num_examples], 1):
                prompt += f"### Example {i}\n"
                prompt += f"Question: {example['question']}\n"
                prompt += f"SPARQL:\n```sparql\n{example['sparql']}\n```\n\n"
        
        # Add the actual question
        prompt += f"\n## User Question\n\nQuestion: {question}\n\nSPARQL:\n"
        
        return prompt
    
    def validate_sparql(self, sparql: str) -> Tuple[bool, str]:
        """
        Validate SPARQL syntax (basic validation).
        
        Args:
            sparql: SPARQL query string
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for basic SPARQL structure
        sparql_clean = sparql.strip()
        
        # Remove markdown code blocks if present
        if sparql_clean.startswith("```"):
            lines = sparql_clean.split('\n')
            # Find content between ``` markers
            start_idx = 1 if lines[0].startswith("```") else 0
            end_idx = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            sparql_clean = '\n'.join(lines[start_idx:end_idx]).strip()
        
        # Check for SELECT/ASK/CONSTRUCT/DESCRIBE
        if not re.search(r'^(SELECT|ASK|CONSTRUCT|DESCRIBE)\b', sparql_clean, re.IGNORECASE | re.MULTILINE):
            return False, "Missing SPARQL query type (SELECT, ASK, CONSTRUCT, or DESCRIBE)"
        
        # Check for WHERE clause (required for SELECT/ASK/CONSTRUCT)
        if re.search(r'^(SELECT|ASK|CONSTRUCT)\b', sparql_clean, re.IGNORECASE | re.MULTILINE):
            if not re.search(r'\bWHERE\b', sparql_clean, re.IGNORECASE):
                return False, "Missing WHERE clause"
        
        # Check for balanced braces
        open_braces = sparql_clean.count('{')
        close_braces = sparql_clean.count('}')
        if open_braces != close_braces:
            return False, f"Unbalanced braces: {open_braces} opening vs {close_braces} closing"
        
        # Check for PREFIX declarations (recommended)
        if not re.search(r'\bPREFIX\b', sparql_clean, re.IGNORECASE):
            # Not a hard error, but a warning
            logger.warning("SPARQL query missing PREFIX declarations")
        
        return True, "Valid"
    
    def generate(self, question: str, use_cache: bool = True) -> Optional[str]:
        """
        Generate SPARQL query from natural language question.
        
        Args:
            question: Natural language question
            use_cache: Whether to use cached results
            
        Returns:
            SPARQL query string, or None on failure
        """
        # Check cache first
        if use_cache and question in self._cache:
            logger.info(f"Cache hit for question: {question[:50]}...")
            return self._cache[question]
        
        # Initialize Gemini if needed
        self._initialize_gemini()
        
        # Build prompt
        prompt = self._build_prompt(question)
        
        # Generate SPARQL with retries
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Generating SPARQL (attempt {attempt + 1}/{self.max_retries})")
                
                response = self._model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": self.temperature,
                        "max_output_tokens": 2048,
                    }
                )
                
                # Extract SPARQL from response
                sparql = response.text.strip()
                
                # Remove markdown code blocks if present
                if sparql.startswith("```"):
                    sparql = self._extract_sparql_from_markdown(sparql)
                
                # Validate SPARQL
                is_valid, error_msg = self.validate_sparql(sparql)
                
                if is_valid:
                    logger.info("Generated valid SPARQL query")
                    
                    # Cache the result
                    if use_cache:
                        self._cache[question] = sparql
                    
                    return sparql
                else:
                    logger.warning(f"Generated invalid SPARQL: {error_msg}")
                    # Retry with error feedback
                    prompt += f"\n\nError in previous attempt: {error_msg}\nPlease provide corrected SPARQL:\n"
                    
            except Exception as e:
                logger.error(f"SPARQL generation failed (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    logger.error(f"Max retries reached for question: {question}")
                    return None
        
        return None
    
    def _extract_sparql_from_markdown(self, text: str) -> str:
        """
        Extract SPARQL query from markdown code block.
        
        Args:
            text: Text potentially containing markdown code block
            
        Returns:
            Extracted SPARQL query
        """
        lines = text.split('\n')
        extracted_lines = []
        in_code_block = False
        
        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                extracted_lines.append(line)
        
        return '\n'.join(extracted_lines).strip() if extracted_lines else text.strip()
    
    def generate_with_fallback(self, question: str, 
                               fallback_query: Optional[str] = None) -> str:
        """
        Generate SPARQL with fallback to deterministic query on failure.
        
        Args:
            question: Natural language question
            fallback_query: Fallback SPARQL query if LLM fails
            
        Returns:
            SPARQL query string (from LLM or fallback)
        """
        # Try LLM generation
        sparql = self.generate(question)
        
        if sparql:
            logger.info("LLM-generated SPARQL successful")
            return sparql
        
        # Fall back to deterministic query
        if fallback_query:
            logger.warning(f"LLM generation failed, using fallback query for: {question}")
            return fallback_query
        
        raise ValueError(f"SPARQL generation failed for question: {question}")
    
    def clear_cache(self) -> None:
        """Clear the query cache."""
        self._cache.clear()
        logger.info("Query cache cleared")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "cache_size": len(self._cache),
            "cache_hits": 0,  # Would need to track separately
        }
