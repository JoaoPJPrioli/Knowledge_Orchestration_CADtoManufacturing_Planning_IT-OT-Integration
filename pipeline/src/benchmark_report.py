"""
LLM Benchmark Report Generation Module
=======================================
Report generation for LLM benchmark testing including matplotlib visualizations,
Markdown summaries, and cost-latency-accuracy analysis.

Reports Generated:
- Model comparison tables
- Accuracy, latency, cost charts
- Cost-latency tradeoff scatter plots
- Accuracy by difficulty/category breakdowns
- Executive summary with recommendations

Usage:
    from benchmark_report import BenchmarkReport
    report = BenchmarkReport(metrics)
    report.generate_charts(output_dir="./reports")
    report.generate_markdown_summary(output_path="./reports/benchmark_summary.md")
"""

import os
import json
import csv
from typing import Dict, List, Any, Optional
from datetime import datetime

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

class BenchmarkReport:
    """
    Benchmark report generator for LLM SPARQL generation testing.
    
    Generates:
    - Visualizations (accuracy, latency, cost comparisons)
    - Markdown summaries with tables
    - JSON/CSV exports
    - Executive summaries with recommendations
    """
    
    def __init__(self, metrics):
        """
        Initialize report generator with evaluation metrics.
        
        Args:
            metrics: EvaluationMetrics instance with benchmark results
        """
        self.metrics = metrics
        self.results = metrics.results
        self.model_comparison = metrics.get_model_comparison()
        self.cost_analysis = metrics.get_cost_analysis()
        self.metrics_by_category = metrics.get_metrics_by_category()
        self.metrics_by_difficulty = metrics.get_metrics_by_difficulty()
        
        # Color palette for charts
        self.colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', 
                       '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    def _create_chart_directory(self, output_dir: str) -> str:
        """
        Create output directory for charts.
        
        Args:
            output_dir: Directory path
            
        Returns:
            Created directory path
        """
        os.makedirs(output_dir, exist_ok=True)
        return output_dir
    
    def generate_accuracy_comparison(self, output_dir: str) -> str:
        """
        Generate accuracy comparison bar chart.
        
        Args:
            output_dir: Output directory
            
        Returns:
            Chart filepath
        """
        output_dir = self._create_chart_directory(output_dir)
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        models = [m["model_name"] for m in self.model_comparison]
        accuracies = [m["accuracy"] for m in self.model_comparison]
        
        bars = ax.bar(models, accuracies, color=self.colors[:len(models)], alpha=0.8, edgecolor='black')
        
        # Add value labels on bars
        for bar, acc in zip(bars, accuracies):
            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.01,
                    f'{acc:.2%}', ha='center', va='bottom', fontweight='bold')
        
        ax.set_ylabel('Accuracy', fontsize=12)
        ax.set_xlabel('Model', fontsize=12)
        ax.set_title('LLM Model Comparison: SPARQL Generation Accuracy', fontsize=14, fontweight='bold')
        ax.set_ylim(0, 1.1)
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        filepath = os.path.join(output_dir, 'accuracy_comparison.png')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        
        return filepath
    
    def generate_latency_comparison(self, output_dir: str) -> str:
        """
        Generate latency comparison bar chart.
        
        Args:
            output_dir: Output directory
            
        Returns:
            Chart filepath
        """
        output_dir = self._create_chart_directory(output_dir)
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        models = [m["model_name"] for m in self.model_comparison]
        latencies = [m["latency_stats"]["mean"] for m in self.model_comparison]
        
        bars = ax.bar(models, latencies, color=self.colors[:len(models)], alpha=0.8, edgecolor='black')
        
        # Add value labels on bars
        for bar, lat in zip(bars, latencies):
            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 50,
                    f'{lat:.0f}ms', ha='center', va='bottom', fontweight='bold')
        
        ax.set_ylabel('Latency (ms)', fontsize=12)
        ax.set_xlabel('Model', fontsize=12)
        ax.set_title('LLM Model Comparison: Query Latency', fontsize=14, fontweight='bold')
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        filepath = os.path.join(output_dir, 'latency_comparison.png')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        
        return filepath
    
    def generate_cost_comparison(self, output_dir: str) -> str:
        """
        Generate cost comparison bar chart.
        
        Args:
            output_dir: Output directory
            
        Returns:
            Chart filepath
        """
        output_dir = self._create_chart_directory(output_dir)
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        models = [m["model_name"] for m in self.model_comparison]
        costs = [m["total_cost"] for m in self.model_comparison]
        
        bars = ax.bar(models, costs, color=self.colors[:len(models)], alpha=0.8, edgecolor='black')
        
        # Add value labels on bars
        for bar, cost in zip(bars, costs):
            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.001,
                    f'${cost:.4f}', ha='center', va='bottom', fontweight='bold')
        
        ax.set_ylabel('Total Cost (USD)', fontsize=12)
        ax.set_xlabel('Model', fontsize=12)
        ax.set_title('LLM Model Comparison: Total API Cost', fontsize=14, fontweight='bold')
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        filepath = os.path.join(output_dir, 'cost_comparison.png')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        
        return filepath
    
    def generate_cost_latency_tradeoff(self, output_dir: str) -> str:
        """
        Generate cost-latency tradeoff scatter plot.
        
        Args:
            output_dir: Output directory
            
        Returns:
            Chart filepath
        """
        output_dir = self._create_chart_directory(output_dir)
        
        fig, ax = plt.subplots(figsize=(10, 8))
        
        models = [m["model_name"] for m in self.model_comparison]
        latencies = [m["latency_stats"]["mean"] for m in self.model_comparison]
        costs = [m["total_cost"] for m in self.model_comparison]
        accuracies = [m["accuracy"] for m in self.model_comparison]
        
        # Scatter plot with bubble size representing accuracy
        scatter = ax.scatter(latencies, costs, s=[a * 5000 for a in accuracies],
                            c=range(len(models)), cmap='viridis', alpha=0.6, edgecolors='black', linewidth=2)
        
        # Add model labels
        for i, model in enumerate(models):
            ax.annotate(model, (latencies[i], costs[i]), fontsize=10, fontweight='bold',
                       ha='center', va='bottom', xytext=(0, 10), textcoords='offset points')
        
        ax.set_xlabel('Latency (ms)', fontsize=12)
        ax.set_ylabel('Total Cost (USD)', fontsize=12)
        ax.set_title('Cost-Latency Tradeoff Analysis\n(Bubble size = Accuracy)', fontsize=14, fontweight='bold')
        ax.grid(alpha=0.3)
        
        plt.tight_layout()
        filepath = os.path.join(output_dir, 'cost_latency_tradeoff.png')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        
        return filepath
    
    def generate_accuracy_by_difficulty(self, output_dir: str) -> str:
        """
        Generate accuracy by difficulty grouped bar chart.
        
        Args:
            output_dir: Output directory
            
        Returns:
            Chart filepath
        """
        output_dir = self._create_chart_directory(output_dir)
        
        fig, ax = plt.subplots(figsize=(12, 7))
        
        difficulties = ['easy', 'medium', 'hard']
        model_names = [m["model_name"] for m in self.model_comparison]
        
        x = np.arange(len(difficulties))
        width = 0.8 / len(model_names)
        
        for i, model in enumerate(self.model_comparison):
            metrics = model.get("metrics_by_difficulty", {})
            accuracies = [metrics.get(d, {}).get("accuracy", 0) for d in difficulties]
            
            bars = ax.bar(x + i * width, accuracies, width, label=model_names[i],
                         color=self.colors[i], alpha=0.8, edgecolor='black')
            
            # Add value labels
            for bar, acc in zip(bars, accuracies):
                if acc > 0:
                    ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.01,
                            f'{acc:.2f}', ha='center', va='bottom', fontsize=8)
        
        ax.set_ylabel('Accuracy', fontsize=12)
        ax.set_xlabel('Query Difficulty', fontsize=12)
        ax.set_title('Accuracy by Query Difficulty', fontsize=14, fontweight='bold')
        ax.set_xticks(x + width * (len(model_names) - 1) / 2)
        ax.set_xticklabels(difficulties)
        ax.legend(title='Models', fontsize=9)
        ax.set_ylim(0, 1.1)
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        filepath = os.path.join(output_dir, 'accuracy_by_difficulty.png')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        
        return filepath
    
    def generate_accuracy_by_category(self, output_dir: str) -> str:
        """
        Generate accuracy by category grouped bar chart.
        
        Args:
            output_dir: Output directory
            
        Returns:
            Chart filepath
        """
        output_dir = self._create_chart_directory(output_dir)
        
        fig, ax = plt.subplots(figsize=(14, 8))
        
        categories = ['feature', 'operation', 'tool', 'sequence', 'complex']
        model_names = [m["model_name"] for m in self.model_comparison]
        
        x = np.arange(len(categories))
        width = 0.8 / len(model_names)
        
        for i, model in enumerate(self.model_comparison):
            metrics = model.get("metrics_by_category", {})
            accuracies = [metrics.get(cat, {}).get("accuracy", 0) for cat in categories]
            
            bars = ax.bar(x + i * width, accuracies, width, label=model_names[i],
                         color=self.colors[i], alpha=0.8, edgecolor='black')
        
        ax.set_ylabel('Accuracy', fontsize=12)
        ax.set_xlabel('Query Category', fontsize=12)
        ax.set_title('Accuracy by Query Category', fontsize=14, fontweight='bold')
        ax.set_xticks(x + width * (len(model_names) - 1) / 2)
        ax.set_xticklabels(categories, rotation=45, ha='right')
        ax.legend(title='Models', fontsize=9)
        ax.set_ylim(0, 1.1)
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        filepath = os.path.join(output_dir, 'accuracy_by_category.png')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        
        return filepath
    
    def generate_all_charts(self, output_dir: str = "./benchmark_reports/charts") -> List[str]:
        """
        Generate all benchmark charts.
        
        Args:
            output_dir: Output directory
            
        Returns:
            List of generated chart filepaths
        """
        charts = [
            self.generate_accuracy_comparison(output_dir),
            self.generate_latency_comparison(output_dir),
            self.generate_cost_comparison(output_dir),
            self.generate_cost_latency_tradeoff(output_dir),
            self.generate_accuracy_by_difficulty(output_dir),
            self.generate_accuracy_by_category(output_dir)
        ]
        
        return charts
    
    def generate_markdown_summary(self, output_path: str = "./benchmark_reports/benchmark_summary.md") -> str:
        """
        Generate comprehensive Markdown summary report.
        
        Args:
            output_path: Output file path
            
        Returns:
            Markdown content
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        summary = self.metrics.get_summary()
        cost_analysis = self.cost_analysis
        error_analysis = self.metrics.get_error_analysis()
        
        markdown = f"""# LLM Benchmark Report: SPARQL Generation for Manufacturing Knowledge Graph

## Executive Summary

**Benchmark Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Total Models Tested:** {len(self.model_comparison)}

**Total Queries:** {summary['total_queries']}

**Overall Accuracy:** {summary['accuracy']:.2%}

**Best Model (by F1 Score):** {self.model_comparison[0]['model_name'] if self.model_comparison else 'N/A'}

---

## Model Comparison Table

| Model | Accuracy | Precision | Recall | F1 Score | Latency (mean) | Total Cost |
|-------|----------|-----------|--------|----------|----------------|------------|
"""
        
        for model in self.model_comparison:
            markdown += f"| {model['model_name']} | {model['accuracy']:.2%} | {model['precision']:.2%} | {model['recall']:.2%} | {model['f1_score']:.2%} | {model['latency_stats']['mean']:.0f}ms | ${model['total_cost']:.4f} |\n"
        
        markdown += f"""
## Cost Analysis

**Total Cost (All Models):** ${cost_analysis['total_cost_all_models']:.4f}

**Most Expensive Model:** {cost_analysis['most_expensive_model']}

**Cheapest Model:** {cost_analysis['cheapest_model']}

| Model | Total Cost | Avg Cost/Query | Queries |
|-------|------------|----------------|---------|
"""
        
        for model, cost_data in cost_analysis['cost_by_model'].items():
            markdown += f"| {model} | ${cost_data['total_cost']:.4f} | ${cost_data['avg_cost_per_query']:.6f} | {cost_data['total_queries']} |\n"
        
        markdown += f"""
## Error Analysis

**Total Errors:** {error_analysis['total_errors']}

**Error Rate:** {error_analysis['error_rate']:.2%}

**Syntax Errors:** {error_analysis['syntax_errors']}

**Semantic Errors:** {error_analysis['semantic_errors']}

### Errors by Category
| Category | Errors |
|----------|--------|
"""
        
        for category, count in error_analysis['errors_by_category'].items():
            markdown += f"| {category} | {count} |\n"
        
        markdown += f"""
### Errors by Difficulty
| Difficulty | Errors |
|------------|--------|
"""
        
        for difficulty, count in error_analysis['errors_by_difficulty'].items():
            markdown += f"| {difficulty} | {count} |\n"
        
        markdown += f"""
## Recommendations

Based on the benchmark results:

1. **Best Overall Model:** {self.model_comparison[0]['model_name'] if self.model_comparison else 'N/A'} (Highest F1 Score)
2. **Best Cost-Effective Model:** {cost_analysis['cheapest_model']} (Lowest Total Cost)
3. **Fastest Model:** {min(self.model_comparison, key=lambda x: x['latency_stats']['mean'])['model_name'] if self.model_comparison else 'N/A'} (Lowest Latency)

## Charts

Generated charts are available in the `charts/` directory:
- `accuracy_comparison.png` - Model accuracy comparison
- `latency_comparison.png` - Model latency comparison
- `cost_comparison.png` - Model cost comparison
- `cost_latency_tradeoff.png` - Cost-latency tradeoff analysis
- `accuracy_by_difficulty.png` - Accuracy by query difficulty
- `accuracy_by_category.png` - Accuracy by query category

---

*Report generated by LLM Benchmark Testing Framework*
"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
        
        return markdown
    
    def export_json(self, output_path: str = "./benchmark_reports/benchmark_results.json") -> str:
        """
        Export complete benchmark results to JSON.
        
        Args:
            output_path: Output file path
            
        Returns:
            JSON filepath
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        export_data = {
            "benchmark_date": datetime.now().isoformat(),
            "summary": self.metrics.get_summary(),
            "model_comparison": self.model_comparison,
            "cost_analysis": self.cost_analysis,
            "metrics_by_category": self.metrics_by_category,
            "metrics_by_difficulty": self.metrics_by_difficulty,
            "error_analysis": self.metrics.get_error_analysis(),
            "total_results": len(self.results)
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        return output_path
    
    def export_csv(self, output_path: str = "./benchmark_reports/benchmark_results.csv") -> str:
        """
        Export benchmark results to CSV.
        
        Args:
            output_path: Output file path
            
        Returns:
            CSV filepath
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'query_id', 'model_name', 'category', 'difficulty',
                'syntax_valid', 'semantic_correct', 'latency_ms', 'cost_usd',
                'timestamp'
            ])
            
            # Data rows
            for result in self.results:
                writer.writerow([
                    result['query_id'],
                    result['model_name'],
                    result['category'],
                    result['difficulty'],
                    result['syntax_valid'],
                    result['semantic_correct'],
                    result['latency_ms'],
                    result['cost_usd'],
                    result['timestamp']
                ])
        
        return output_path
    
    def generate_full_report(self, output_dir: str = "./benchmark_reports") -> Dict[str, str]:
        """
        Generate complete benchmark report with all charts and summaries.
        
        Args:
            output_dir: Output directory
            
        Returns:
            Dict with generated file paths
        """
        generated_files = {}
        
        # Generate charts
        charts = self.generate_all_charts(os.path.join(output_dir, 'charts'))
        generated_files['charts'] = charts
        
        # Generate Markdown summary
        markdown_path = self.generate_markdown_summary(os.path.join(output_dir, 'benchmark_summary.md'))
        generated_files['markdown_summary'] = os.path.join(output_dir, 'benchmark_summary.md')
        
        # Export JSON
        json_path = self.export_json(os.path.join(output_dir, 'benchmark_results.json'))
        generated_files['json_export'] = json_path
        
        # Export CSV
        csv_path = self.export_csv(os.path.join(output_dir, 'benchmark_results.csv'))
        generated_files['csv_export'] = csv_path
        
        return generated_files
