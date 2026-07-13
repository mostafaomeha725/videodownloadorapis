import 'package:flutter_bloc/flutter_bloc.dart';
import '../../domain/downloader_repository.dart';
import 'downloader_state.dart';

class DownloaderCubit extends Cubit<DownloaderState> {
  final DownloaderRepository repository;

  DownloaderCubit({required this.repository}) : super(DownloaderInitial());

  Future<void> downloadVideo(String url) async {
    if (url.trim().isEmpty) {
      emit(const DownloaderError(message: 'URL cannot be empty.'));
      return;
    }

    // Basic URL validation
    final uri = Uri.tryParse(url);
    if (uri == null || !uri.hasAbsolutePath || !uri.scheme.startsWith('http')) {
      emit(const DownloaderError(message: 'Please enter a valid URL.'));
      return;
    }

    emit(DownloaderLoading());

    try {
      final videoDetails = await repository.downloadVideo(url);
      emit(DownloaderSuccess(videoDetails: videoDetails));
    } catch (e) {
      // Remove the "Exception: " prefix if present
      String errorMsg = e.toString();
      if (errorMsg.startsWith('Exception: ')) {
        errorMsg = errorMsg.substring(11);
      }
      emit(DownloaderError(message: errorMsg));
    }
  }

  void reset() {
    emit(DownloaderInitial());
  }
}
