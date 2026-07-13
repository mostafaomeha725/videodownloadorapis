import 'package:dio/dio.dart';
import '../../../core/api/dio_client.dart';
import 'downloader_model.dart';

class DownloaderApi {
  final DioClient dioClient;

  DownloaderApi({required this.dioClient});

  Future<VideoDetailsModel> downloadVideo(String url) async {
    try {
      final response = await dioClient.dio.post(
        '/download',
        data: {'url': url},
      );

      if (response.statusCode == 200 && response.data != null) {
        return VideoDetailsModel.fromJson(response.data);
      } else {
        throw Exception('Failed to get video details');
      }
    } on DioException catch (e) {
      if (e.response != null && e.response?.data != null) {
        final data = e.response?.data;
        String message = 'An error occurred';
        if (data is Map<String, dynamic>) {
          if (data.containsKey('message')) {
            message = data['message'].toString();
          } else if (data.containsKey('detail')) {
            final detail = data['detail'];
            if (detail is String) {
              message = detail;
            } else if (detail is List && detail.isNotEmpty) {
              message = detail[0]['msg']?.toString() ?? 'Validation Error';
            }
          }
        }
        throw Exception(message);
      }
      throw Exception('Network error: ${e.message}');
    } catch (e) {
      throw Exception(e.toString());
    }
  }
}
