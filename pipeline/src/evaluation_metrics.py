"""
LLM Evaluation Metrics Module
==============================
Metrics calculation for LLM benchmark testing including accuracy,
precision, recall, F1 score, latency, and cost analysis.

Metrics Calculated:
- Accuracy: Overall correctness of SPARQL generation
- Precision: Correct predictions / Total predictions
- Recall: Correct predictions / Total actual positives
- F1 Score: Harmonic mean of precision and recall
- Latency: Query response time (ms)
- Cost: API call cost (USD)
- Syntax Validity: SPARQL syntax correctness
- Semantic Correctness: Query result accuracy

Usage:
    from evaluation_metrics import EvaluationMetrics
    metrics = EvaluationMetrics()
    metrics.add_result(query_id=1, predicted="SELECT ...", expected="SELECT ...", latency_ms=1200)
    summary = metrics.get_summary()
"""

import time
import re
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from collections import defaultdict

class EvaluationMetrics:
    """
    Evaluation metrics calculator for LLM SPARQL generation benchmarks.
    
    Tracks and calculates:
    - Accuracy, precision, recall, F1 score
    - Latency statistics (mean, median, p95, p99)
    - Cost analysis per model and query
    - Syntax validity and semantic correctness
    """
    
    def __init__(self):
        """Initialize evaluation metrics tracker."""
        self.results: List[Dict[str, Any]] = []
        self.start_time = datetime.now()
        
    def add_result(self, query_id: int, model_name: str, predicted: str, 
                   expected: str, latency_ms: float, cost_usd: float = 0.0,
                   syntax_valid: bool = True, semantic_correct: bool = True,
                   category: str = "", difficulty: str = "",
                   ground_truth: Any = None, predicted_result: Any = None):
        """
        Add a benchmark result.
        
        Args:
            query_id: Query identifier
            model_name: Model name (e.g., "Gemini 2.0 Flash")
            predicted: Generated SPARQL query
            expected: Expected SPARQL query (ground truth)
            latency_ms: Query latency in milliseconds
            cost_usd: API call cost in USD
            syntax_valid: Whether generated SPARQL is syntactically valid
            semantic_correct: Whether query results match expected
            category: Query category (feature, operation, tool, sequence, complex)
            difficulty: Query difficulty (easy, medium, hard)
            ground_truth: Ground truth query results
            predicted_result: Predicted query results
        """
        result = {
            "query_id": query_id,
            "model_name": model_name,
            "predicted": predicted,
            "expected": expected,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
            "syntax_valid": syntax_valid,
            "semantic_correct": semantic_correct,
            "category": category,
            "difficulty": difficulty,
            "ground_truth": ground_truth,
            "predicted_result": predicted_result,
            "timestamp": datetime.now().isoformat()
        }
        
        self.results.append(result)
    
    def _normalize_sparql(self, sparql: str) -> str:
        """
        Normalize SPARQL query for comparison.
        
        Args:
            sparql: Raw SPARQL query
            
        Returns:
            Normalized SPARQL string
        """
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', sparql.strip())
        
        # Normalize prefixes
        normalized = re.sub(r'PREFIX\s+mfg:\s*<[^>]+>', 'PREFIX mfg: <http://onto.brep.org/manufacturing#>', normalized)
        normalized = re.sub(r'PREFIX\s+rdf:\s*<[^>]+>', 'PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>', normalized)
        
        return normalized.lower()
    
    def _calculate_accuracy(self, results: List[Dict[str, Any]]) -> float:
        """
        Calculate accuracy: correct predictions / total predictions.
        
        Args:
            results: List of result dictionaries
            
        Returns:
            Accuracy score (0.0 to 1.0)
        """
        if not results:
            return 0.0
        
        correct = sum(1 for r in results if r["semantic_correct"])
        return correct / len(results)
    
    def _calculate_precision(self, results: List[Dict[str, Any]]) -> float:
        """
        Calculate precision: true positives / (true positives + false positives).
        
        Args:
            results: List of result dictionaries
            
        Returns:
            Precision score (0.0 to 1.0)
        """
        if not results:
            return 0.0
        
        # True positives: syntax valid AND semantic correct
        true_positives = sum(1 for r in results if r["syntax_valid"] and r["semantic_correct"])
        
        # Total predictions that claimed to be correct (syntax valid)
        predicted_positives = sum(1 for r in results if r["syntax_valid"])
        
        if predicted_positives == 0:
            return 0.0
        
        return true_positives / predicted_positives
    
    def _calculate_recall(self, results: List[Dict[str, Any]]) -> float:
        """
        Calculate recall: true positives / (true positives + false negatives).
        
        Args:
            results: List of result dictionaries
            
        Returns:
            Recall score (0.0 to 1.0)
        """
        if not results:
            return 0.0
        
        # True positives: syntax valid AND semantic correct
        true_positives = sum(1 for r in results if r["syntax_valid"] and r["semantic_correct"])
        
        # Total actual positives (should be correct)
        actual_positives = len(results)
        
        if actual_positives == 0:
            return 0.0
        
        return true_positives / actual_positives
    
    def _calculate_f1(self, precision: float, recall: float) -> float:
        """
        Calculate F1 score: harmonic mean of precision and recall.
        
        Args:
            precision: Precision score
            recall: Recall score
            
        Returns:
            F1 score (0.0 to 1.0)
        """
        if precision + recall == 0:
            return 0.0
        
        return 2 * (precision * recall) / (precision + recall)
    
    def _calculate_latency_stats(self, latencies: List[float]) -> Dict[str, float]:
        """
        Calculate latency statistics.
        
        Args:
            latencies: List of latency values in milliseconds
            
        Returns:
            Dict with mean, median, p95, p99, min, max
        """
        if not latencies:
            return {"mean": 0, "median": 0, "p95": 0, "p99": 0, "min": 0, "max": 0}
        
        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)
        
        mean = sum(sorted_latencies) / n
        median = sorted_latencies[n // 2]
        p95 = sorted_latencies[int(n * 0.95)]
        p99 = sorted_latencies[int(n * 0.99)]
        min_val = sorted_latencies[0]
        max_val = sorted_latencies[-1]
        
        return {
            "mean": round(mean, 2),
            "median": round(median, 2),
            "p95": round(p95, 2),
            "p99": round(p99, 2),
            "min": round(min_val, 2),
            "max": round(max_val, 2)
        }
    
    def get_summary(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get summary metrics for all models or a specific model.
        
        Args:
            model_name: Optional model name to filter
            
        Returns:
            Dict with summary metrics
        """
        results = self.results
        if model_name:
            results = [r for r in results if r["model_name"] == model_name]
        
        if not results:
            return {
                "model_name": model_name or "all",
                "total_queries": 0,
                "accuracy": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "f1_score": 0.0,
                "latency_stats": {},
                "total_cost": 0.0,
                "avg_cost_per_query": 0.0
            }
        
        accuracy = self._calculate_accuracy(results)
        precision = self._calculate_precision(results)
        recall = self._calculate_recall(results)
        f1 = self._calculate_f1(precision, recall)
        
        latencies = [r["latency_ms"] for r in results]
        latency_stats = self._calculate_latency_stats(latencies)
        
        total_cost = sum(r["cost_usd"] for r in results)
        avg_cost = total_cost / len(results)
        
        syntax_valid_count = sum(1 for r in results if r["syntax_valid"])
        semantic_correct_count = sum(1 for r in results if r["semantic_correct"])
        
        return {
            "model_name": model_name or "all",
            "total_queries": len(results),
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "latency_stats": latency_stats,
            "total_cost": round(total_cost, 6),
            "avg_cost_per_query": round(avg_cost, 6),
            "syntax_valid_count": syntax_valid_count,
            "semantic_correct_count": semantic_correct_count,
            "syntax_validity_rate": round(syntax_valid_count / len(results), 4),
            "semantic_correctness_rate": round(semantic_correct_count / len(results), 4)
        }
    
    def get_metrics_by_category(self, model_name: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Get metrics grouped by query category.
        
        Args:
            model_name: Optional model name to filter
            
        Returns:
            Dict mapping category to metrics
        """
        results = self.results
        if model_name:
            results = [r for r in results if r["model_name"] == model_name]
        
        categories = defaultdict(list)
        for r in results:
            categories[r["category"]].append(r)
        
        metrics_by_category = {}
        for category, cat_results in categories.items():
            accuracy = self._calculate_accuracy(cat_results)
            precision = self._calculate_precision(cat_results)
            recall = self._calculate_recall(cat_results)
            f1 = self._calculate_f1(precision, recall)
            
            latencies = [r["latency_ms"] for r in cat_results]
            latency_stats = self._calculate_latency_stats(latencies)
            
            metrics_by_category[category] = {
                "total_queries": len(cat_results),
                "accuracy": round(accuracy, 4),
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1_score": round(f1, 4),
                "latency_stats": latency_stats
            }
        
        return metrics_by_category
    
    def get_metrics_by_difficulty(self, model_name: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Get metrics grouped by query difficulty.
        
        Args:
            model_name: Optional model name to filter
            
        Returns:
            Dict mapping difficulty to metrics
        """
        results = self.results
        if model_name:
            results = [r for r in results if r["model_name"] == model_name]
        
        difficulties = defaultdict(list)
        for r in results:
            difficulties[r["difficulty"]].append(r)
        
        metrics_by_difficulty = {}
        for difficulty, diff_results in difficulties.items():
            accuracy = self._calculate_accuracy(diff_results)
            precision = self._calculate_precision(diff_results)
            recall = self._calculate_recall(diff_results)
            f1 = self._calculate_f1(precision, recall)
            
            latencies = [r["latency_ms"] for r in diff_results]
            latency_stats = self._calculate_latency_stats(latencies)
            
            metrics_by_difficulty[difficulty] = {
                "total_queries": len(diff_results),
                "accuracy": round(accuracy, 4),
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1_score": round(f1, 4),
                "latency_stats": latency_stats
            }
        
        return metrics_by_difficulty
    
    def get_model_comparison(self) -> List[Dict[str, Any]]:
        """
        Get comparison metrics across all models.
        
        Returns:
            List of summary metrics for each model
        """
        models = set(r["model_name"] for r in self.results)
        
        comparison = []
        for model in models:
            summary = self.get_summary(model)
            comparison.append(summary)
        
        # Sort by F1 score (descending)
        comparison.sort(key=lambda x: x["f1_score"], reverse=True)
        
        return comparison
    
    def get_cost_analysis(self) -> Dict[str, Any]:
        """
        Get cost analysis across all models.
        
        Returns:
            Dict with cost analysis
        """
        models = set(r["model_name"] for r in self.results)
        
        cost_by_model = {}
        for model in models:
            model_results = [r for r in self.results if r["model_name"] == model]
            total_cost = sum(r["cost_usd"] for r in model_results)
            avg_cost = total_cost / len(model_results) if model_results else 0
            
            cost_by_model[model] = {
                "total_cost": round(total_cost, 6),
                "avg_cost_per_query": round(avg_cost, 6),
                "total_queries": len(model_results)
            }
        
        total_cost_all = sum(r["cost_usd"] for r in self.results)
        
        return {
            "cost_by_model": cost_by_model,
            "total_cost_all_models": round(total_cost_all, 6),
            "most_expensive_model": max(cost_by_model.items(), key=lambda x: x[1]["total_cost"])[0] if cost_by_model else None,
            "cheapest_model": min(cost_by_model.items(), key=lambda x: x[1]["total_cost"])[0] if cost_by_model else None
        }
    
    def get_error_analysis(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get error analysis for failed queries.
        
        Args:
            model_name: Optional model name to filter
            
        Returns:
            Dict with error analysis
        """
        results = self.results
        if model_name:
            results = [r for r in results if r["model_name"] == model_name]
        
        errors = [r for r in results if not r["semantic_correct"]]
        
        syntax_errors = [r for r in results if not r["syntax_valid"]]
        semantic_errors = [r for r in errors if r["syntax_valid"]]  # Syntax OK but wrong results
        
        errors_by_category = defaultdict(int)
        errors_by_difficulty = defaultdict(int)
        
        for r in errors:
            errors_by_category[r["category"]] += 1
            errors_by_difficulty[r["difficulty"]] += 1
        
        return {
            "total_errors": len(errors),
            "syntax_errors": len(syntax_errors),
            "semantic_errors": len(semantic_errors),
            "error_rate": round(len(errors) / len(results), 4) if results else 0,
            "errors_by_category": dict(errors_by_category),
            "errors_by_difficulty": dict(errors_by_difficulty),
            "failed_query_ids": [r["query_id"] for r in errors]
        }
    
    def export_results(self, filepath: str = "benchmark_results.json") -> str:
        """
        Export all results to JSON file.
        
        Args:
            filepath: Output file path
            
        Returns:
            Filepath of exported results
        """
        import json
        
        export_data = {
            "benchmark_start_time": self.start_time.isoformat(),
            "benchmark_end_time": datetime.now().isoformat(),
            "total_results": len(self.results),
            "results": self.results,
            "summary": self.get_summary(),
            "model_comparison": self.get_model_comparison(),
            "cost_analysis": self.get_cost_analysis()
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        return filepath
