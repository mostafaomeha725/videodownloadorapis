import 'package:equatable/equatable.dart';

class VideoQuality extends Equatable {
  final String quality;
  final String downloadUrl;
  final int qualityIndex;

  const VideoQuality({
    required this.quality,
    required this.downloadUrl,
    this.qualityIndex = 0,
  });

  @override
  List<Object?> get props => [quality, downloadUrl, qualityIndex];
}

class VideoDetails extends Equatable {
  final String title;
  final String thumbnail;
  final String duration;
  final String platform;
  final List<VideoQuality> qualities;

  const VideoDetails({
    required this.title,
    required this.thumbnail,
    required this.duration,
    required this.platform,
    required this.qualities,
  });

  @override
  List<Object?> get props => [title, thumbnail, duration, platform, qualities];
}
