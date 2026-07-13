import 'package:get_it/get_it.dart';
import '../api/dio_client.dart';
import '../../features/downloader/data/downloader_api.dart';
import '../../features/downloader/data/downloader_repository_impl.dart';
import '../../features/downloader/domain/downloader_repository.dart';
import '../../features/downloader/presentation/cubit/downloader_cubit.dart';

final sl = GetIt.instance;

Future<void> init() async {
  // Core
  sl.registerLazySingleton<DioClient>(() => DioClient());

  // API
  sl.registerLazySingleton<DownloaderApi>(() => DownloaderApi(dioClient: sl()));

  // Repository
  sl.registerLazySingleton<DownloaderRepository>(
    () => DownloaderRepositoryImpl(api: sl()),
  );

  // Cubit
  sl.registerFactory(() => DownloaderCubit(repository: sl()));
}
