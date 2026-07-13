import '../domain/downloader_entity.dart';

class VideoQualityModel extends VideoQuality {
  const VideoQualityModel({
    required super.quality,
    required super.downloadUrl,
    super.qualityIndex,
  });

  factory VideoQualityModel.fromJson(Map<String, dynamic> json) {
    return VideoQualityModel(
      quality: json['quality'] ?? '',
      downloadUrl: json['url'] ?? '',
      qualityIndex: json['quality_index'] ?? 0,
    );
  }
}

class VideoDetailsModel extends VideoDetails {
  const VideoDetailsModel({
    required super.title,
    required super.thumbnail,
    required super.duration,
    required super.platform,
    required super.qualities,
  });

  factory VideoDetailsModel.fromJson(Map<String, dynamic> json) {
    return VideoDetailsModel(
      title: json['title'] ?? 'Unknown Title',
      thumbnail: json['thumbnail'] ?? '',
      duration: json['duration']?.toString() ?? '',
      platform: json['platform'] ?? 'Unknown',
      qualities: (json['qualities'] as List<dynamic>?)
              ?.map((q) => VideoQualityModel.fromJson(q))
              .toList() ??
          [],
    );
  }
}
