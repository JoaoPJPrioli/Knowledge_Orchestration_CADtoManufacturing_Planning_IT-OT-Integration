"""
LLM Benchmark Testing Script
=============================
Multi-model benchmark runner for testing LLM SPARQL generation efficiency.

This script:
- Loads manufacturing knowledge graph data
- Tests multiple Gemini models (2.0 Flash, 2.5 Pro, 2.5 Flash)
- Generates SPARQL queries from natural language
- Measures accuracy, latency, cost, and efficiency
- Generates comprehensive benchmark reports

Usage:
    # Run all benchmarks
    python test_llm_benchmarks.py
    
    # Run specific model only
    python test_llm_benchmarks.py --model "Gemini 2.0 Flash"
    
    # Run specific query category
    python test_llm_benchmarks.py --category "complex"
    
    # Custom output directory
    python test_llm_benchmarks.py --output-dir "./custom_reports"

Requirements:
    - GEMINI_API_KEY environment variable set
    - Manufacturing KG data available (data/motor_data/eixo.step)
    - Dependencies installed (pip install -r requirements.txt)
"""

import os
import sys
import time
import json
import argparse
from typing import Dict, List, Any, Optional
from datetime import datetime

# BASE_DIR is the project root (this file lives in tests/, one level down).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

from benchmark_config import MODEL_CONFIGS, TEST_QUERIES, EVALUATION_SETTINGS, get_model_config, get_queries_by_category
from evaluation_metrics import EvaluationMetrics
from benchmark_report import BenchmarkReport
from sparql_generator import SparqlGenerator
from kg_builder import ManufacturingKG
from rdf_triplestore import ManufacturingTriplestore

class LLMBenchmarkRunner:
    """
    Multi-model LLM benchmark runner for SPARQL generation.
    
    Tests multiple Gemini models against manufacturing knowledge graph queries,
    measuring accuracy, latency, cost, and efficiency metrics.
    """
    
    def __init__(self, model_names: Optional[List[str]] = None, 
                 query_category: Optional[str] = None,
                 output_dir: str = "./benchmark_reports"):
        """
        Initialize benchmark runner.
        
        Args:
            model_names: List of model names to test (None = all models)
            query_category: Query category to test (None = all categories)
            output_dir: Output directory for reports
        """
        self.model_names = model_names or [m["name"] for m in MODEL_CONFIGS]
        self.query_category = query_category
        self.output_dir = output_dir
        self.metrics = EvaluationMetrics()
        
        # Setup test queries
        if query_category:
            self.test_queries = get_queries_by_category(query_category)
            print(f"  ✓ Loaded {len(self.test_queries)} queries from category: {query_category}")
        else:
            self.test_queries = TEST_QUERIES
            print(f"  ✓ Loaded {len(self.test_queries)} test queries (all categories)")
        
        # Initialize KG and triplestore
        self.kg = None
        self.triplestore = None
        self.query_engine = None
        
        os.makedirs(output_dir, exist_ok=True)
        print(f"  ✓ Output directory: {output_dir}")
    
    def setup_knowledge_graph(self, step_file: str = os.path.join(BASE_DIR, 'data', 'motor_data', 'eixo.step')):
        """
        Setup manufacturing knowledge graph and RDF triplestore.
        
        Args:
            step_file: Path to STEP file for feature extraction
        """
        print("\n=== Setting Up Knowledge Graph ===")
        
        try:
            # Build NetworkX knowledge graph
            self.kg = ManufacturingKG()
            self.kg.load_step_file(step_file)
            self.kg.build_knowledge_graph()
            
            print(f"  ✓ NetworkX KG built: {self.kg.get_node_count()} nodes, {self.kg.get_edge_count()} edges")
            
            # Export to RDF triplestore
            print("  → Exporting to RDF triplestore...")
            self.triplestore = self.kg.export_to_rdf(
                filepath=os.path.join(self.output_dir, "manufacturing_kg.ttl")
            )
            
            print(f"  ✓ RDF Triplestore created: {self.triplestore.get_triple_count()} triples")
            
            # Setup query engine with SPARQL backend
            from orchestrator import QueryEngine
            self.query_engine = QueryEngine(self.kg, self.triplestore)
            self.query_engine.switch_backend('networkx')  # Use NetworkX for ground truth
            
            print("  ✓ QueryEngine initialized with dual backend support")
            
        except Exception as e:
            print(f"  ✗ Error setting up knowledge graph: {e}")
            print("  → Running in SPARQL-only mode (using example queries)")
    
    def get_ground_truth_result(self, query: Dict[str, Any]) -> Any:
        """
        Get ground truth result using NetworkX backend.
        
        Args:
            query: Test query dictionary
            
        Returns:
            Ground truth query result
        """
        if not self.query_engine:
            return None
        
        question = query["question"].lower()
        
        try:
            # Extract feature ID from question if present
            feature_id = None
            for word in question.split():
                if word.isdigit():
                    feature_id = int(word)
                    break
            
            # Route to appropriate query method
            if "operations" in question and feature_id:
                return self.query_engine.query_operations_for_feature(feature_id)
            elif "tools" in question and "operation" in question:
                return self.query_engine.query_tool_for_operation("turning")
            elif "sequence" in question or "order" in question:
                return self.query_engine.query_machining_sequence()
            elif "feature" in question and feature_id:
                return self.query_engine.query_feature_details(feature_id)
            else:
                return self.query_engine.query_multi_hop(feature_id or 1001)
        
        except Exception as e:
            print(f"    ⚠ Error getting ground truth: {e}")
            return None
    
    def validate_sparql_result(self, generated_sparql: str, query: Dict[str, Any]) -> Dict[str, bool]:
        """
        Validate generated SPARQL query against ground truth.
        
        Args:
            generated_sparql: Generated SPARQL query string
            query: Test query dictionary
            
        Returns:
            Dict with syntax_valid and semantic_correct flags
        """
        validation = {
            "syntax_valid": False,
            "semantic_correct": False
        }
        
        if not self.triplestore or not generated_sparql:
            return validation
        
        try:
            # Test 1: Syntax validation (execute query)
            result = self.triplestore.execute_sparql(generated_sparql)
            validation["syntax_valid"] = True
            
            # Test 2: Semantic validation (compare with ground truth)
            ground_truth = self.get_ground_truth_result(query)
            
            if ground_truth is not None and result is not None:
                # Basic validation: both should return results (or both empty)
                if (len(result) > 0) == (len(ground_truth) > 0):
                    validation["semantic_correct"] = True
                
                # Advanced validation: check result patterns match
                expected_pattern = query.get("expected_pattern", "")
                if expected_pattern and expected_pattern.lower() in generated_sparql.lower():
                    validation["semantic_correct"] = True
        
        except Exception as e:
            print(f"    ⚠ Validation error: {e}")
            validation["syntax_valid"] = False
            validation["semantic_correct"] = False
        
        return validation
    
    def test_model(self, model_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test a single model against all queries.
        
        Args:
            model_config: Model configuration dictionary
            
        Returns:
            Dict with model test results
        """
        model_name = model_config["name"]
        print(f"\n{'='*80}")
        print(f"Testing Model: {model_name}")
        print(f"{'='*80}")
        
        # Initialize SPARQL generator for this model
        try:
            generator = SparqlGenerator(
                model_name=model_config["model_id"],
                temperature=model_config["temperature"],
                max_output_tokens=model_config["max_output_tokens"]
            )
            print(f"  ✓ Initialized {model_name} (temperature={model_config['temperature']})")
            
        except Exception as e:
            print(f"  ✗ Failed to initialize {model_name}: {e}")
            print(f"  → Skipping this model")
            return {"model_name": model_name, "error": str(e)}
        
        # Test each query
        for i, query in enumerate(self.test_queries, 1):
            query_id = query["id"]
            question = query["question"]
            category = query["category"]
            difficulty = query["difficulty"]
            
            print(f"\n  [{i}/{len(self.test_queries)}] Query {query_id}: {question[:60]}...")
            print(f"    Category: {category}, Difficulty: {difficulty}")
            
            # Measure latency
            start_time = time.time()
            
            try:
                # Generate SPARQL query
                generated_sparql = generator.generate(question)
                
                # Calculate latency
                latency_ms = (time.time() - start_time) * 1000
                
                # Estimate cost (based on tokens)
                input_tokens = len(question.split()) * 1.3  # Rough estimate
                output_tokens = len(generated_sparql.split()) * 1.1
                cost_usd = (
                    (input_tokens / 1_000_000) * model_config["cost_per_1m_input"] +
                    (output_tokens / 1_000_000) * model_config["cost_per_1m_output"]
                )
                
                # Validate result
                validation = self.validate_sparql_result(generated_sparql, query)
                
                # Add result to metrics
                self.metrics.add_result(
                    query_id=query_id,
                    model_name=model_name,
                    predicted=generated_sparql,
                    expected=query.get("expected_pattern", ""),
                    latency_ms=latency_ms,
                    cost_usd=cost_usd,
                    syntax_valid=validation["syntax_valid"],
                    semantic_correct=validation["semantic_correct"],
                    category=category,
                    difficulty=difficulty,
                    ground_truth=self.get_ground_truth_result(query),
                    predicted_result=generated_sparql
                )
                
                # Print result
                status = "✓" if validation["semantic_correct"] else ("✓" if validation["syntax_valid"] else "✗")
                print(f"    {status} Latency: {latency_ms:.0f}ms, Syntax: {validation['syntax_valid']}, Semantic: {validation['semantic_correct']}")
                
            except Exception as e:
                print(f"    ✗ Error: {e}")
                
                # Record failed attempt
                latency_ms = (time.time() - start_time) * 1000
                self.metrics.add_result(
                    query_id=query_id,
                    model_name=model_name,
                    predicted="",
                    expected=query.get("expected_pattern", ""),
                    latency_ms=latency_ms,
                    cost_usd=0.0,
                    syntax_valid=False,
                    semantic_correct=False,
                    category=category,
                    difficulty=difficulty
                )
            
            # Small delay between queries to avoid rate limiting
            time.sleep(0.5)
        
        # Print model summary
        model_summary = self.metrics.get_summary(model_name)
        print(f"\n  {model_name} Summary:")
        print(f"    Accuracy: {model_summary['accuracy']:.2%}")
        print(f"    F1 Score: {model_summary['f1_score']:.2%}")
        print(f"    Mean Latency: {model_summary['latency_stats']['mean']:.0f}ms")
        print(f"    Total Cost: ${model_summary['total_cost']:.4f}")
        
        return model_summary
    
    def run_benchmarks(self):
        """
        Run benchmarks for all configured models.
        
        Returns:
            List of model summaries
        """
        print("\n" + "="*80)
        print("LLM BENCHMARK TESTING: SPARQL Generation for Manufacturing KG")
        print("="*80)
        print(f"\nStart Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Models to Test: {len(self.model_names)}")
        print(f"Test Queries: {len(self.test_queries)}")
        print(f"Output Directory: {self.output_dir}")
        
        # Setup knowledge graph
        self.setup_knowledge_graph()
        
        # Test each model
        model_summaries = []
        for model_name in self.model_names:
            try:
                model_config = get_model_config(model_name)
                summary = self.test_model(model_config)
                model_summaries.append(summary)
                
            except Exception as e:
                print(f"\n✗ Error testing {model_name}: {e}")
                model_summaries.append({
                    "model_name": model_name,
                    "error": str(e)
                })
        
        # Calculate total time
        end_time = datetime.now()
        total_time = (end_time - self.metrics.start_time).total_seconds()
        
        print(f"\n{'='*80}")
        print(f"BENCHMARK COMPLETE")
        print(f"{'='*80}")
        print(f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total Time: {total_time:.1f} seconds")
        
        return model_summaries
    
    def generate_reports(self) -> Dict[str, str]:
        """
        Generate comprehensive benchmark reports.
        
        Returns:
            Dict with generated file paths
        """
        print(f"\n{'='*80}")
        print("GENERATING BENCHMARK REPORTS")
        print(f"{'='*80}")
        
        # Create report generator
        report = BenchmarkReport(self.metrics)
        
        # Generate full report
        generated_files = report.generate_full_report(self.output_dir)
        
        print(f"\n  ✓ Generated {len(generated_files['charts'])} charts")
        print(f"  ✓ Markdown summary: {generated_files['markdown_summary']}")
        print(f"  ✓ JSON export: {generated_files['json_export']}")
        print(f"  ✓ CSV export: {generated_files['csv_export']}")
        
        # Print final comparison
        print(f"\n{'='*80}")
        print("FINAL MODEL COMPARISON")
        print(f"{'='*80}")
        
        comparison = self.metrics.get_model_comparison()
        print(f"\n{'Model':<25} {'Accuracy':<12} {'F1 Score':<12} {'Latency':<12} {'Cost':<12}")
        print("-" * 73)
        
        for model in comparison:
            print(f"{model['model_name']:<25} "
                  f"{model['accuracy']:<12.2%} "
                  f"{model['f1_score']:<12.2%} "
                  f"{model['latency_stats']['mean']:<12.0f}ms "
                  f"${model['total_cost']:<11.4f}")
        
        return generated_files
    
    def print_recommendations(self):
        """Print model recommendations based on benchmark results."""
        comparison = self.metrics.get_model_comparison()
        cost_analysis = self.metrics.get_cost_analysis()
        
        if not comparison:
            print("\n⚠ No benchmark results available for recommendations")
            return
        
        print(f"\n{'='*80}")
        print("RECOMMENDATIONS")
        print(f"{'='*80}")
        
        # Best overall (highest F1)
        best_overall = comparison[0]
        print(f"\n🏆 Best Overall Model: {best_overall['model_name']}")
        print(f"   F1 Score: {best_overall['f1_score']:.2%}")
        print(f"   Accuracy: {best_overall['accuracy']:.2%}")
        
        # Best cost-effective
        cheapest = cost_analysis['cheapest_model']
        print(f"\n💰 Most Cost-Effective: {cheapest}")
        print(f"   Total Cost: ${cost_analysis['cost_by_model'][cheapest]['total_cost']:.4f}")
        
        # Fastest
        fastest = min(comparison, key=lambda x: x['latency_stats']['mean'])
        print(f"\n⚡ Fastest Model: {fastest['model_name']}")
        print(f"   Mean Latency: {fastest['latency_stats']['mean']:.0f}ms")
        
        # Production recommendation
        print(f"\n📋 Production Recommendation:")
        if best_overall['f1_score'] > 0.8 and best_overall['latency_stats']['mean'] < 5000:
            print(f"   ✓ Use {best_overall['model_name']} for production (high accuracy, good speed)")
        elif cheapest and cost_analysis['cost_by_model'][cheapest]['total_cost'] < 0.1:
            print(f"   ✓ Use {cheapest} for production (cost-effective)")
        else:
            print(f"   ⚠ Consider fine-tuning or prompt engineering to improve results")
        
        # Category-specific recommendations
        print(f"\n📊 Category-Specific Insights:")
        metrics_by_category = self.metrics.get_metrics_by_category()
        for category, cat_metrics in metrics_by_category.items():
            best_model_for_category = max(
                comparison,
                key=lambda x: x.get('metrics_by_category', {}).get(category, {}).get('accuracy', 0)
            )
            print(f"   {category}: {best_model_for_category['model_name']} "
                  f"(accuracy: {cat_metrics['accuracy']:.2%})")


def main():
    """Main entry point for benchmark testing."""
    parser = argparse.ArgumentParser(
        description='LLM Benchmark Testing for SPARQL Generation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all benchmarks
  python test_llm_benchmarks.py
  
  # Test specific model
  python test_llm_benchmarks.py --model "Gemini 2.0 Flash"
  
  # Test specific query category
  python test_llm_benchmarks.py --category complex
  
  # Custom output directory
  python test_llm_benchmarks.py --output-dir ./my_reports
        """
    )
    
    parser.add_argument(
        '--model',
        type=str,
        nargs='+',
        default=None,
        help='Model names to test (default: all models)'
    )
    
    parser.add_argument(
        '--category',
        type=str,
        choices=['feature', 'operation', 'tool', 'sequence', 'complex'],
        default=None,
        help='Query category to test (default: all categories)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='./benchmark_reports',
        help='Output directory for reports (default: ./benchmark_reports)'
    )
    
    args = parser.parse_args()
    
    # Check for API key
    if not os.environ.get('GEMINI_API_KEY'):
        print("⚠ WARNING: GEMINI_API_KEY environment variable not set")
        print("  Please set your API key: set GEMINI_API_KEY=your_key_here")
        print("  Benchmarks will run in simulation mode")
        input("\nPress Enter to continue in simulation mode...")
    
    # Initialize and run benchmarks
    runner = LLMBenchmarkRunner(
        model_names=args.model,
        query_category=args.category,
        output_dir=args.output_dir
    )
    
    # Run benchmarks
    model_summaries = runner.run_benchmarks()
    
    # Generate reports
    generated_files = runner.generate_reports()
    
    # Print recommendations
    runner.print_recommendations()
    
    print(f"\n{'='*80}")
    print("BENCHMARK TESTING COMPLETE")
    print(f"{'='*80}")
    print(f"\nReports saved to: {args.output_dir}")
    print(f"  - benchmark_summary.md (Markdown report)")
    print(f"  - benchmark_results.json (JSON data)")
    print(f"  - benchmark_results.csv (CSV data)")
    print(f"  - charts/ (Visualization charts)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
