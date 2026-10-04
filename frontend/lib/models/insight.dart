class SentimentInfo {
  final double scoreMoyen;
  final String interpretation;
  final int nombreArticles;

  SentimentInfo({
    required this.scoreMoyen,
    required this.interpretation,
    required this.nombreArticles,
  });

  factory SentimentInfo.fromJson(Map<String, dynamic> json) {
    return SentimentInfo(
      scoreMoyen: (json['score_moyen'] as num).toDouble(),
      interpretation: json['interpretation'],
      nombreArticles: json['nombre_articles'],
    );
  }
}

class Insight {
  final String symbol;
  final double prixActuel;
  final String tendance;
  final double volatilite;
  final double maxDrawdown;
  final SentimentInfo sentiment;
  final double? probabiliteHausse;
  final String analyseLlm;
  final String disclaimer;

  Insight({
    required this.symbol,
    required this.prixActuel,
    required this.tendance,
    required this.volatilite,
    required this.maxDrawdown,
    required this.sentiment,
    required this.probabiliteHausse,
    required this.analyseLlm,
    required this.disclaimer,
  });

  factory Insight.fromJson(Map<String, dynamic> json) {
    return Insight(
      symbol: json['symbol'],
      prixActuel: (json['prix_actuel'] as num).toDouble(),
      tendance: json['tendance'],
      volatilite: (json['volatilite_annualisee_pct'] as num).toDouble(),
      maxDrawdown: (json['max_drawdown_pct'] as num).toDouble(),
      sentiment: SentimentInfo.fromJson(json['sentiment_30j']),
      probabiliteHausse: json['probabilite_hausse_pct'] != null
          ? (json['probabilite_hausse_pct'] as num).toDouble()
          : null,
      analyseLlm: json['analyse_llm'],
      disclaimer: json['disclaimer'],
    );
  }
}