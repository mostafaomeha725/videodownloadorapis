import '../domain/downloader_entity.dart';
import '../domain/downloader_repository.dart';
import 'downloader_api.dart';

class DownloaderRepositoryImpl implements DownloaderRepository {
  final DownloaderApi api;

  DownloaderRepositoryImpl({required this.api});

  @override
  Future<VideoDetails> downloadVideo(String url) async {
    return await api.downloadVideo(url);
  }
}
