import 'downloader_entity.dart';

abstract class DownloaderRepository {
  Future<VideoDetails> downloadVideo(String url);
}
